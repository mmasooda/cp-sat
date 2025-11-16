"""Rule engine that interprets workbook guidance and builds CP-SAT models."""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from excel_reader import SheetData, XLSXReader

try:  # Optional dependency; solver not available during tests but code must run.
    from ortools.sat.python import cp_model
except Exception:  # pragma: no cover - handled gracefully at runtime
    cp_model = None  # type: ignore


# ---------------------------------------------------------------------------
# Data structures representing workbook content
# ---------------------------------------------------------------------------


@dataclass
class ModuleDefinition:
    """Represents a module entry from the 4100ES module workbook."""

    model_number: str
    description: str
    compatible_panels: List[str]
    compatible_protocols: List[str]
    total_point_capacity: Optional[str]
    circuit_capacity: Optional[str]
    supervisory_current: Optional[float]
    alarm_current: Optional[float]
    supported_speakers: Optional[str]
    circuits: Optional[str]
    compulsory_main_modules: List[str]
    module_role: str
    physical_size: str
    mounted_on: str
    dependencies: List[str]
    specification_categories: List[str]
    keywords: List[str]
    price: float = 0.0
    internal_space: float = 0.0
    door_space: float = 0.0

    def matches_keyword(self, keyword: str) -> bool:
        keyword_lower = keyword.lower()
        haystacks = [
            self.description.lower(),
            " ".join(self.specification_categories).lower(),
            " ".join(self.keywords).lower(),
        ]
        return any(keyword_lower in haystack for haystack in haystacks)

    @property
    def block_count(self) -> float:
        if self.internal_space or self.door_space:
            return self.internal_space + self.door_space
        if not self.physical_size:
            return 0.0
        size_lower = self.physical_size.lower()
        digits = "".join(ch for ch in size_lower if ch.isdigit() or ch == ".")
        try:
            return float(digits) if digits else 0.0
        except ValueError:
            return 0.0


@dataclass
class PlacementRule:
    """Human-readable placement rule extracted from overview workbook."""

    path: Tuple[str, ...]
    text: str


@dataclass
class PanelRequirements:
    """Summarised requirements derived from Q&A answers and project BOQ."""

    protocol: str
    voice_evacuation: bool
    prefer_addressable_nac: bool
    has_fire_phone: bool
    has_led_switches: bool
    has_smoke_management: bool
    has_door_holder_220vac: bool
    monitor_leds: bool
    graphics_control: bool
    speaker_wattage: float
    speaker_count: int
    fire_phone_circuits: int
    nac_circuits_required: int
    slc_loops_required: int
    relay_count: int
    loop_device_count: int
    nac_device_count: int
    idnet_modules_required: int
    requires_printer: bool
    requires_network_cards: bool
    network_links: int
    nac_class_a: bool
    speaker_class_a: bool
    constant_supervision: bool
    requires_led_packages: bool
    fire_damper_control: bool
    dual_amplifier_per_zone: bool
    backup_amp_one_to_one: bool
    backup_amp_one_for_all: bool


@dataclass
class OptimizationResult:
    """Result returned by the rule engine for a single panel."""

    category_requirements: Dict[str, int]
    module_selection: Dict[str, int]
    estimated_cost: float
    solver_status: str
    space_usage: Dict[str, float]
    bay_allocation: Dict[str, int]


class RuleRepository:
    """Loads module metadata, placement rules, and pricing overrides."""

    def __init__(
        self,
        module_workbook: str,
        placement_workbook: str,
        pricing_overrides: Optional[str] = None,
    ) -> None:
        self.module_workbook = module_workbook
        self.placement_workbook = placement_workbook
        self.modules: List[ModuleDefinition] = []
        self.placement_rules: List[PlacementRule] = []
        self.category_to_modules: Dict[str, List[ModuleDefinition]] = {}
        self.module_index: Dict[str, ModuleDefinition] = {}
        self.module_prices: Dict[str, float] = {}
        self.category_prices: Dict[str, float] = {}
        self._load_pricing_overrides(pricing_overrides)
        self._load_modules()
        self._load_placement_rules()

    # ------------------------------------------------------------------
    def _load_pricing_overrides(self, pricing_path: Optional[str]) -> None:
        if pricing_path and os.path.exists(pricing_path):
            with open(pricing_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.module_prices = {
                key: float(value) for key, value in data.get("module_overrides", {}).items()
            }
            self.category_prices = {
                key: float(value)
                for key, value in data.get("category_defaults", {}).items()
            }
        else:
            # Provide conservative defaults that encourage minimal selections.
            self.category_prices = {
                "Master Controller": 4500.0,
                "Power Supplies": 1200.0,
                "EPS & Accessories": 1600.0,
                "IDNet Modules": 950.0,
                "Notification Modules": 900.0,
                "Audio Options (S4100-0104)": 1800.0,
                "Telephone (S4100-0104)": 750.0,
                "LED-Switch (4100-0032)": 650.0,
                "Relay Modules": 500.0,
                "VCC Interfaces (S4100-0104)": 900.0,
            }

    # ------------------------------------------------------------------
    def _load_modules(self) -> None:
        reader = XLSXReader(self.module_workbook)
        sheet = reader.read_sheet()
        module_lookup: Dict[str, ModuleDefinition] = {}

        for record in sheet.records():
            model_number = record.get("Module Model Number", "").strip()
            if not model_number:
                continue

            description = record.get("Description", "").strip()
            compatible_panels = [
                value.strip()
                for value in record.get("compatible with Panel", "").split(",")
                if value.strip()
            ]
            compatible_protocols = [
                value.strip()
                for value in record.get("compatible with Protocol", "").split(",")
                if value.strip()
            ]
            total_point_capacity = record.get("Total Point Capacity Possible") or None
            circuit_capacity = record.get("Point Capacity / Circuit Capacity") or None
            supervisory_current = _safe_float(record.get("Supervisory Current", ""))
            alarm_current = _safe_float(record.get("Alarm Current", ""))
            supported_speakers = record.get("Supports which Speakers") or None
            circuits = record.get("Circuits/Points") or None
            compulsory_main = [
                value.strip()
                for value in record.get("Possible Compulsory Main Modules", "").split(",")
                if value.strip()
            ]
            module_role = record.get("Is it Main module or sub-module mounted on main", "").strip()
            physical_size = record.get("Physical Size", "").strip()
            mounted_on = record.get("Mounted ON", "").strip()
            dependencies = [
                value.strip()
                for value in record.get("Another Module needed to function", "").split(",")
                if value.strip()
            ]
            spec_categories = [
                value.strip()
                for value in record.get("Specification Descriptions", "").split(",")
                if value.strip()
            ]
            keywords = [
                value.strip()
                for value in record.get("Keywords associated with the module", "").split(",")
                if value.strip()
            ]

            price = self.module_prices.get(model_number)
            if price is None and spec_categories:
                price = self.category_prices.get(spec_categories[0], 0.0)
            if price is None:
                price = 0.0

            internal_space, door_space = _derive_space_requirements(
                model_number, physical_size, mounted_on
            )

            if model_number in module_lookup:
                module = module_lookup[model_number]
                if description and not module.description:
                    module.description = description
                module.compatible_panels = _merge_unique(
                    module.compatible_panels, compatible_panels
                )
                module.compatible_protocols = _merge_unique(
                    module.compatible_protocols, compatible_protocols
                )
                if total_point_capacity and not module.total_point_capacity:
                    module.total_point_capacity = total_point_capacity
                if circuit_capacity and not module.circuit_capacity:
                    module.circuit_capacity = circuit_capacity
                if supervisory_current is not None and module.supervisory_current is None:
                    module.supervisory_current = supervisory_current
                if alarm_current is not None and module.alarm_current is None:
                    module.alarm_current = alarm_current
                if supported_speakers and not module.supported_speakers:
                    module.supported_speakers = supported_speakers
                if circuits and not module.circuits:
                    module.circuits = circuits
                module.compulsory_main_modules = _merge_unique(
                    module.compulsory_main_modules, compulsory_main
                )
                module.dependencies = _merge_unique(module.dependencies, dependencies)
                module.specification_categories = _merge_unique(
                    module.specification_categories, spec_categories
                )
                module.keywords = _merge_unique(module.keywords, keywords)
                if not module.module_role:
                    module.module_role = module_role
                if not module.physical_size:
                    module.physical_size = physical_size
                if not module.mounted_on:
                    module.mounted_on = mounted_on
                if module.price <= 0 and price > 0:
                    module.price = price
                module.internal_space = max(module.internal_space, internal_space)
                module.door_space = max(module.door_space, door_space)
                continue

            module_lookup[model_number] = ModuleDefinition(
                model_number=model_number,
                description=description,
                compatible_panels=compatible_panels,
                compatible_protocols=compatible_protocols,
                total_point_capacity=total_point_capacity,
                circuit_capacity=circuit_capacity,
                supervisory_current=supervisory_current,
                alarm_current=alarm_current,
                supported_speakers=supported_speakers,
                circuits=circuits,
                compulsory_main_modules=compulsory_main,
                module_role=module_role,
                physical_size=physical_size,
                mounted_on=mounted_on,
                dependencies=dependencies,
                specification_categories=spec_categories,
                keywords=keywords,
                price=price,
                internal_space=internal_space,
                door_space=door_space,
            )

        for synthetic in SYNTHETIC_MODULES:
            if synthetic.model_number in module_lookup:
                existing = module_lookup[synthetic.model_number]
                if existing.price <= 0 and synthetic.price > 0:
                    existing.price = synthetic.price
                existing.specification_categories = _merge_unique(
                    existing.specification_categories, synthetic.specification_categories
                )
                existing.keywords = _merge_unique(existing.keywords, synthetic.keywords)
            else:
                module_lookup[synthetic.model_number] = synthetic

        self.modules = list(module_lookup.values())
        self.category_to_modules = {}
        for module in self.modules:
            for category in module.specification_categories:
                self.category_to_modules.setdefault(category, []).append(module)
        self.module_index = {module.model_number: module for module in self.modules}

    # ------------------------------------------------------------------
    def _load_placement_rules(self) -> None:
        reader = XLSXReader(self.placement_workbook)
        sheet = reader.read_sheet()
        hierarchy: List[str] = [""] * len(sheet.rows[0]) if sheet.rows else []

        for row in sheet.rows:
            for idx, cell in enumerate(row):
                value = cell.strip()
                if not value:
                    continue
                hierarchy[idx] = value
                for reset_idx in range(idx + 1, len(hierarchy)):
                    hierarchy[reset_idx] = ""
                path = tuple(filter(None, hierarchy[:idx]))
                if path:
                    self.placement_rules.append(PlacementRule(path=path, text=value))
                break

    # ------------------------------------------------------------------
    def ensure_rule_keywords(self, required_keywords: Iterable[str]) -> None:
        catalogue = " ".join(rule.text.lower() for rule in self.placement_rules)
        missing = [keyword for keyword in required_keywords if keyword.lower() not in catalogue]
        if missing:
            raise ValueError(
                "Missing critical placement guidelines in workbook: " + ", ".join(missing)
            )

    # ------------------------------------------------------------------
    def get_module(self, model_number: str) -> Optional[ModuleDefinition]:
        return self.module_index.get(model_number)

    def estimate_cost(self, model_number: str, quantity: int = 1) -> float:
        module = self.get_module(model_number)
        if module and module.price > 0:
            return module.price * quantity
        if model_number in self.module_prices:
            return self.module_prices[model_number] * quantity
        if module and module.specification_categories:
            category = module.specification_categories[0]
            if category in self.category_prices:
                return self.category_prices[category] * quantity
        # Fallback guardrail cost encourages solver to keep selections minimal.
        return 1000.0 * quantity


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    cleaned = "".join(ch for ch in str(value) if ch.isdigit() or ch in {".", "-"})
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


SPACE_OVERRIDES: Dict[str, Tuple[float, float]] = {
    # Audio/telephone modules with microphones occupy both internal slots and door space.
    "4100-1243": (2.0, 1.0),  # Master microphone assembly
    "4100-1252": (1.0, 1.0),  # Audio/telephone operator interface
    "4100-1253": (2.0, 1.0),  # Combined audio + microphone interface
    "4100-1254": (2.0, 1.0),  # Two-channel audio operator interface
    "4100-1270": (2.0, 1.0),  # Fire fighters telephone control
    "4100-9620": (8.0, 1.0),  # Basic analog audio w/ microphone reserves a bay
}

ENCLOSURE_DEFINITIONS = [
    {
        "model_number": "4100-9401",
        "description": "4100ES 1-bay cabinet backbox",
        "category": "Cabinet Assemblies",
        "keywords": ["cabinet", "backbox", "1-bay"],
        "price": 950.0,
        "size": 1,
        "family": "cabinet",
    },
    {
        "model_number": "4100-9402",
        "description": "4100ES 2-bay cabinet backbox",
        "category": "Cabinet Assemblies",
        "keywords": ["cabinet", "backbox", "2-bay"],
        "price": 1200.0,
        "size": 2,
        "family": "cabinet",
    },
    {
        "model_number": "4100-9403",
        "description": "4100ES 3-bay cabinet backbox",
        "category": "Cabinet Assemblies",
        "keywords": ["cabinet", "backbox", "3-bay"],
        "price": 1450.0,
        "size": 3,
        "family": "cabinet",
    },
    {
        "model_number": "4100-9404",
        "description": "4100ES 1-bay solid door",
        "category": "Cabinet Doors",
        "keywords": ["door", "solid", "1-bay"],
        "price": 420.0,
        "size": 1,
        "family": "door_solid",
    },
    {
        "model_number": "4100-9405",
        "description": "4100ES 2-bay solid door",
        "category": "Cabinet Doors",
        "keywords": ["door", "solid", "2-bay"],
        "price": 520.0,
        "size": 2,
        "family": "door_solid",
    },
    {
        "model_number": "4100-9406",
        "description": "4100ES 3-bay solid door",
        "category": "Cabinet Doors",
        "keywords": ["door", "solid", "3-bay"],
        "price": 620.0,
        "size": 3,
        "family": "door_solid",
    },
    {
        "model_number": "4100-9407",
        "description": "4100ES 1-bay glass door",
        "category": "Cabinet Doors",
        "keywords": ["door", "glass", "1-bay"],
        "price": 560.0,
        "size": 1,
        "family": "door_glass",
    },
    {
        "model_number": "4100-9408",
        "description": "4100ES 2-bay glass door",
        "category": "Cabinet Doors",
        "keywords": ["door", "glass", "2-bay"],
        "price": 690.0,
        "size": 2,
        "family": "door_glass",
    },
    {
        "model_number": "4100-9409",
        "description": "4100ES 3-bay glass door",
        "category": "Cabinet Doors",
        "keywords": ["door", "glass", "3-bay"],
        "price": 820.0,
        "size": 3,
        "family": "door_glass",
    },
]

def _build_enclosure_maps():
    cabinet: Dict[int, str] = {}
    solid: Dict[int, str] = {}
    glass: Dict[int, str] = {}
    for entry in ENCLOSURE_DEFINITIONS:
        size = int(entry["size"])
        model = entry["model_number"]
        if entry["family"] == "cabinet":
            cabinet[size] = model
        elif entry["family"] == "door_solid":
            solid[size] = model
        elif entry["family"] == "door_glass":
            glass[size] = model
    return cabinet, solid, glass


CABINET_SIZE_TO_MODEL, SOLID_DOOR_SIZE_TO_MODEL, GLASS_DOOR_SIZE_TO_MODEL = _build_enclosure_maps()

SYNTHETIC_MODULES: List[ModuleDefinition] = []
for entry in ENCLOSURE_DEFINITIONS:
    SYNTHETIC_MODULES.append(
        ModuleDefinition(
            model_number=entry["model_number"],
            description=entry["description"],
            compatible_panels=["4100ES"],
            compatible_protocols=["IDNet2", "MX"],
            total_point_capacity=None,
            circuit_capacity=None,
            supervisory_current=None,
            alarm_current=None,
            supported_speakers=None,
            circuits=None,
            compulsory_main_modules=[],
            module_role="Cabinet",
            physical_size="",
            mounted_on="",
            dependencies=[],
            specification_categories=[entry["category"]],
            keywords=list(entry["keywords"]),
            price=float(entry["price"]),
        )
    )

MODULE_ALIASES = {
    "MASTER_CONTROLLER": "4100-9701",
    "IDNET_DUAL_LOOP": "4100-3109",
    "POWER_SUPPLY_MAIN": "4100-5311",
    "POWER_SUPPLY_EXPANSION": "4100-5325",
    "IDNAC_MODULE": "4100-5451",
    "CONVENTIONAL_NAC": "4100-5450",
    "NAC_CLASS_A": "4100-1246",
    "NAC_SUPERVISION": "4100-1266",
    "AUDIO_BASE": "4100-9620",
    "AUDIO_OPERATOR": "4100-1254",
    "AUDIO_AMPLIFIER": "4100-1248",
    "AUDIO_CLASS_A": "4100-1249",
    "FIRE_PHONE": "4100-1270",
    "LED_CONTROLLER": "4100-1288",
    "PRINTER": "4100-1293",
    "RS232": "4100-6038",
    "NETWORK_INTERFACE": "4100-6080",
    "RELAY_MODULE": "4100-6033",
    "RELAY_ZONE": "4100-5013",
}

INTERNAL_BLOCKS_PER_BAY = 8.0  # Blocks A-H
DOOR_SLOTS_PER_BAY = 8.0  # Front door slots 1-8

_NUMERIC_SLOT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*slots?", re.IGNORECASE)
_NUMERIC_BLOCK_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*blocks?", re.IGNORECASE)
_SLOT_INLINE_PATTERN = re.compile(r"slot\s*([0-9]+)", re.IGNORECASE)
_BLOCK_INLINE_PATTERN = re.compile(r"block\s*([a-h]+)", re.IGNORECASE)


def _merge_unique(values: List[str], additions: Iterable[str]) -> List[str]:
    lookup = {value.lower(): value for value in values if value}
    for value in additions:
        if not value:
            continue
        key = value.lower()
        if key not in lookup:
            lookup[key] = value
    return list(lookup.values())


def _inline_slot_usage(text: str) -> float:
    collapsed = text.replace(" ", "")
    values = []
    for match in _SLOT_INLINE_PATTERN.finditer(collapsed):
        digits = match.group(1)
        if not digits:
            continue
        values.append(float(max(1, len(set(digits)))))
    return max(values, default=0.0)


def _inline_block_usage(text: str) -> float:
    collapsed = text.replace(" ", "").lower()
    values = []
    for match in _BLOCK_INLINE_PATTERN.finditer(collapsed):
        letters = [ch for ch in match.group(1) if "a" <= ch <= "h"]
        if not letters:
            continue
        values.append(float(max(1, len(set(letters)))))
    return max(values, default=0.0)


def _numeric_keyword_usage(pattern: re.Pattern[str], text: str) -> float:
    value = 0.0
    for match in pattern.finditer(text):
        try:
            quantity = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if 0 < quantity <= 32:
            value = max(value, quantity)
    return value


def _derive_space_requirements(
    model_number: str, physical_size: str, mounted_on: str
) -> Tuple[float, float]:
    override = SPACE_OVERRIDES.get(model_number)
    if override:
        return override

    text = (physical_size or "").strip()
    mount = (mounted_on or "").strip().lower()
    if not text and mount not in {"internal", "door", "both"}:
        return (0.0, 0.0)

    numeric_slots = _numeric_keyword_usage(_NUMERIC_SLOT_PATTERN, text)
    numeric_blocks = _numeric_keyword_usage(_NUMERIC_BLOCK_PATTERN, text)
    inline_slots = _inline_slot_usage(text)
    inline_blocks = _inline_block_usage(text)

    base_internal = max(numeric_blocks, inline_blocks, numeric_slots, inline_slots)
    base_door = max(numeric_slots, inline_slots, numeric_blocks if numeric_slots == 0 else 0.0, inline_blocks if inline_slots == 0 else 0.0)

    internal = 0.0
    door = 0.0

    if mount in {"internal", "both"}:
        internal = base_internal
    if mount in {"door", "both"}:
        door = base_door

    if mount in {"internal", "both"} and internal <= 0:
        internal = 1.0 if mount != "door" else 0.0
    if mount in {"door", "both"} and door <= 0:
        door = 1.0 if mount != "internal" else 0.0

    if mount == "both":
        internal = max(internal, 1.0)
        door = max(door, 1.0)

    return (internal, door)


def _allocate_enclosure_sizes(
    required_bays: int, size_to_model: Dict[int, str]
) -> Dict[str, int]:
    plan: Dict[str, int] = {}
    if required_bays <= 0 or not size_to_model:
        return plan
    sizes = sorted(size_to_model.keys(), reverse=True)
    remaining = required_bays
    for idx, size in enumerate(sizes):
        if remaining <= 0:
            break
        count = remaining // size
        if count == 0 and idx == len(sizes) - 1:
            count = 1
        if count <= 0:
            continue
        model = size_to_model[size]
        plan[model] = plan.get(model, 0) + count
        remaining -= size * count
    if remaining > 0:
        smallest = sizes[-1]
        model = size_to_model[smallest]
        plan[model] = plan.get(model, 0) + 1
    return plan


# ---------------------------------------------------------------------------
# Rule engine main class
# ---------------------------------------------------------------------------


class RuleEngine:
    """High level orchestrator for deriving optimisation problems."""

    def __init__(
        self,
        module_workbook: str = "4100ES_All_Modules_Complete MX rev2.xlsx",
        placement_workbook: str = "4100ES Overview of Placement Rules.xlsx",
        pricing_overrides: Optional[str] = None,
    ) -> None:
        self.repository = RuleRepository(
            module_workbook=module_workbook,
            placement_workbook=placement_workbook,
            pricing_overrides=pricing_overrides,
        )
        # Ensure critical placement instructions were loaded to avoid silent omissions.
        self.repository.ensure_rule_keywords(
            [
                "power supply",
                "audio controller",
                "amplifier",
                "display",
                "annunciator",
            ]
        )

    # ------------------------------------------------------------------
    def build_requirements(self, answers, boq) -> PanelRequirements:
        loop_devices = (
            boq.smoke_detector
            + boq.heat_detector
            + boq.duct_detector
            + boq.beam_detector
            + boq.manual_station
            + boq.monitor_module
            + boq.control_relay
        )
        idnet_modules_required = max(1, math.ceil(loop_devices / 500)) if loop_devices else 1
        slc_loops_required = idnet_modules_required * 2

        nac_devices = (
            boq.horn_strobe
            + boq.strobe_only
            + boq.horn_only
            + boq.addressable_horn_strobe
            + boq.addressable_strobe
            + boq.speaker_strobe
        )
        nac_circuits_required = math.ceil(nac_devices / 14) if nac_devices else 0

        speaker_total = boq.speaker + boq.speaker_strobe
        relay_count = boq.control_relay + answers.smoke_management_relay_count
        if answers.fire_damper_feedback or answers.fire_damper_led_indication:
            relay_count = max(relay_count, 8)
        if answers.door_holder_voltage == "220vac":
            relay_count += 1

        speaker_wattage = answers.speaker_wattage
        if speaker_wattage <= 0 and speaker_total > 0:
            speaker_wattage = speaker_total * 15  # conservative default per device

        fire_phone_circuits = math.ceil(boq.fire_phone_jack / 10) if boq.fire_phone_jack else 0

        requires_network_cards = (
            answers.has_graphics_command_center
            or answers.graphics_software_type in {"view_only", "full_control"}
            or answers.network_type != "none"
        )
        network_links = 0
        if requires_network_cards:
            network_links = 1
        if answers.network_type in {"smfo", "mmfo"}:
            network_links = max(network_links, 2)
        if answers.graphics_software_type == "full_control":
            network_links = max(network_links, 2)

        requires_led_packages = (
            answers.audio_control_led_switches
            or answers.monitor_modules_with_leds
            or answers.fire_damper_led_indication
        )

        return PanelRequirements(
            protocol=answers.protocol.value,
            voice_evacuation=answers.audio_type.name.lower() != "no_audio",
            prefer_addressable_nac=answers.use_addressable_nac,
            has_fire_phone=answers.has_fire_phone or fire_phone_circuits > 0,
            has_led_switches=answers.audio_control_led_switches or answers.monitor_modules_with_leds,
            has_smoke_management=answers.has_smoke_management,
            has_door_holder_220vac=(answers.door_holder_voltage == "220vac"),
            monitor_leds=answers.monitor_modules_with_leds,
            graphics_control=answers.graphics_software_type == "full_control",
            speaker_wattage=speaker_wattage,
            speaker_count=speaker_total,
            fire_phone_circuits=fire_phone_circuits,
            nac_circuits_required=nac_circuits_required,
            slc_loops_required=slc_loops_required,
            relay_count=relay_count,
            loop_device_count=loop_devices,
            nac_device_count=nac_devices,
            idnet_modules_required=idnet_modules_required,
            requires_printer=answers.has_panel_printer,
            requires_network_cards=requires_network_cards,
            network_links=network_links,
            nac_class_a=answers.nac_class_a_wiring,
            speaker_class_a=answers.speaker_class_a_wiring,
            constant_supervision=answers.constant_supervision_speaker,
            requires_led_packages=requires_led_packages,
            fire_damper_control=(answers.fire_damper_feedback or answers.fire_damper_led_indication),
            dual_amplifier_per_zone=getattr(answers, "dual_amplifier_per_zone", False),
            backup_amp_one_to_one=getattr(answers, "backup_amplifier_one_to_one", False),
            backup_amp_one_for_all=getattr(answers, "backup_amplifier_one_for_all", False),
        )

    # ------------------------------------------------------------------
    def derive_category_requirements(self, requirements: PanelRequirements) -> Dict[str, int]:
        category_requirements: Dict[str, int] = {}

        def ensure(category: str, quantity: int) -> None:
            if quantity <= 0:
                return
            category_requirements[category] = max(category_requirements.get(category, 0), quantity)

        ensure("Master Controller", 1)
        ensure(
            "Power Supplies",
            max(1, math.ceil(max(requirements.nac_circuits_required, 1) / 3)),
        )
        nac_power_padding = math.ceil(requirements.nac_device_count / 56) if requirements.nac_device_count else 0
        ensure("EPS & Accessories", max(1, math.ceil(requirements.speaker_wattage / 400) + nac_power_padding))
        ensure("IDNet Modules", requirements.idnet_modules_required)

        if requirements.nac_circuits_required:
            if requirements.prefer_addressable_nac:
                ensure(
                    "Notification Modules",
                    max(1, math.ceil(requirements.nac_circuits_required / 2)),
                )
            else:
                ensure(
                    "Notification Modules",
                    max(1, math.ceil(requirements.nac_circuits_required / 3)),
                )

        if requirements.voice_evacuation:
            audio_modules = max(1, math.ceil(requirements.speaker_wattage / 100))
            ensure("Audio Options (S4100-0104)", audio_modules)
            ensure("VCC Interfaces (S4100-0104)", 1)

        if requirements.has_fire_phone:
            ensure("Telephone (S4100-0104)", max(1, requirements.fire_phone_circuits))

        if requirements.requires_led_packages:
            ensure("LED-Switch (4100-0032)", 1)

        if requirements.has_smoke_management or requirements.relay_count:
            ensure("Relay Modules", max(1, math.ceil(max(1, requirements.relay_count) / 3)))

        if requirements.graphics_control:
            ensure("Master Controller", 1)  # additional CPU loading accounted by duplicate requirement

        if requirements.has_door_holder_220vac:
            ensure("Relay Modules", category_requirements.get("Relay Modules", 0) + 1)

        # Remove zero entries explicitly.
        return {key: value for key, value in category_requirements.items() if value > 0}

    # ------------------------------------------------------------------
    def _summarise_space_usage(
        self, module_selection: Dict[str, int]
    ) -> Tuple[Dict[str, float], Dict[str, int]]:
        internal = 0.0
        door = 0.0
        for model_number, quantity in module_selection.items():
            module = self.repository.get_module(model_number)
            if not module:
                continue
            internal += module.internal_space * quantity
            door += module.door_space * quantity

        space_usage = {
            "internal_blocks": internal,
            "door_slots": door,
        }
        bay_allocation = {
            "internal_bays": math.ceil(internal / INTERNAL_BLOCKS_PER_BAY)
            if internal > 0
            else 0,
            "door_bays": math.ceil(door / DOOR_SLOTS_PER_BAY) if door > 0 else 0,
        }
        bay_allocation["recommended_bays"] = max(
            bay_allocation["internal_bays"], bay_allocation["door_bays"]
        )
        return space_usage, bay_allocation

    # ------------------------------------------------------------------
    def _derive_specific_modules(self, requirements: PanelRequirements) -> Dict[str, int]:
        plan: Dict[str, int] = {}

        def add(model: str, quantity: float) -> None:
            if quantity <= 0:
                return
            plan[model] = max(plan.get(model, 0), int(math.ceil(quantity)))

        add(MODULE_ALIASES["MASTER_CONTROLLER"], 1)
        add(MODULE_ALIASES["POWER_SUPPLY_MAIN"], 1)
        add(MODULE_ALIASES["IDNET_DUAL_LOOP"], requirements.idnet_modules_required)

        if requirements.idnet_modules_required > 1:
            add(
                MODULE_ALIASES["POWER_SUPPLY_EXPANSION"],
                requirements.idnet_modules_required - 1,
            )

        if requirements.nac_circuits_required:
            if requirements.prefer_addressable_nac:
                add(
                    MODULE_ALIASES["IDNAC_MODULE"],
                    math.ceil(requirements.nac_circuits_required / 2),
                )
            else:
                add(
                    MODULE_ALIASES["CONVENTIONAL_NAC"],
                    math.ceil(requirements.nac_circuits_required / 3),
                )
        if requirements.nac_class_a:
            add(
                MODULE_ALIASES["NAC_CLASS_A"],
                max(1, math.ceil(requirements.nac_circuits_required / 3)),
            )
        if requirements.constant_supervision:
            add(
                MODULE_ALIASES["NAC_SUPERVISION"],
                max(1, math.ceil(requirements.nac_circuits_required / 4)),
            )

        if requirements.voice_evacuation:
            add(MODULE_ALIASES["AUDIO_BASE"], 1)
            add(MODULE_ALIASES["AUDIO_OPERATOR"], 1)
            amplifiers = max(1, math.ceil(requirements.speaker_wattage / 100))
            if requirements.backup_amp_one_to_one or requirements.dual_amplifier_per_zone:
                amplifiers *= 2
            elif requirements.backup_amp_one_for_all:
                amplifiers += 1
            add(MODULE_ALIASES["AUDIO_AMPLIFIER"], amplifiers)
            if requirements.speaker_class_a:
                add(
                    MODULE_ALIASES["AUDIO_CLASS_A"],
                    max(1, math.ceil(requirements.speaker_count / 2)),
                )

        if requirements.has_fire_phone:
            add(
                MODULE_ALIASES["FIRE_PHONE"],
                max(1, math.ceil(max(1, requirements.fire_phone_circuits) / 3)),
            )

        if requirements.requires_led_packages:
            add(MODULE_ALIASES["LED_CONTROLLER"], 1)

        if requirements.requires_printer:
            add(MODULE_ALIASES["PRINTER"], 1)
            add(MODULE_ALIASES["RS232"], 1)

        if requirements.requires_network_cards:
            add(MODULE_ALIASES["NETWORK_INTERFACE"], max(1, requirements.network_links))

        total_relays = requirements.relay_count
        if requirements.has_door_holder_220vac:
            total_relays = max(total_relays, requirements.relay_count + 1)
        if requirements.fire_damper_control:
            add(
                MODULE_ALIASES["RELAY_ZONE"],
                max(1, math.ceil(max(8, total_relays) / 8)),
            )
        elif total_relays:
            add(MODULE_ALIASES["RELAY_MODULE"], max(1, math.ceil(total_relays / 3)))

        return plan

    # ------------------------------------------------------------------
    def _derive_enclosure_modules(
        self, module_selection: Dict[str, int]
    ) -> Dict[str, int]:
        space_usage, bay_allocation = self._summarise_space_usage(module_selection)
        required_bays = max(1, int(bay_allocation.get("recommended_bays", 0)))
        plan: Dict[str, int] = {}

        def merge(source: Dict[str, int]) -> None:
            for model, quantity in source.items():
                if quantity <= 0:
                    continue
                plan[model] = plan.get(model, 0) + quantity

        merge(_allocate_enclosure_sizes(required_bays, CABINET_SIZE_TO_MODEL))
        door_map = (
            GLASS_DOOR_SIZE_TO_MODEL
            if space_usage.get("door_slots", 0.0) > 0
            else SOLID_DOOR_SIZE_TO_MODEL
        )
        merge(_allocate_enclosure_sizes(required_bays, door_map))
        return plan

    # ------------------------------------------------------------------
    def _build_solver(self, category_requirements: Dict[str, int]) -> Optional[OptimizationResult]:
        if cp_model is None:
            return None

        model = cp_model.CpModel()
        variables: Dict[str, cp_model.IntVar] = {}
        for module in self.repository.modules:
            variables[module.model_number] = model.NewIntVar(0, 20, module.model_number)

        # For each required category ensure sufficient quantity is purchased.
        for category, min_quantity in category_requirements.items():
            modules = self.repository.category_to_modules.get(category, [])
            if not modules:
                continue
            model.Add(
                sum(variables[module.model_number] for module in modules) >= min_quantity
            )

        # Objective: minimise total price (or block count if price missing).
        objective_terms = []
        for module in self.repository.modules:
            unit_cost = module.price if module.price > 0 else module.block_count or 1.0
            weight = max(1, int(round(unit_cost * 100)))
            objective_terms.append(weight * variables[module.model_number])
        model.Minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10
        status = solver.Solve(model)

        module_selection: Dict[str, int] = {}
        total_cost = 0.0
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for module in self.repository.modules:
                quantity = solver.Value(variables[module.model_number])
                if quantity:
                    module_selection[module.model_number] = quantity
                    total_cost += module.price * quantity
            status_name = cp_model.OPTIMAL if status == cp_model.OPTIMAL else "FEASIBLE"
        else:
            status_name = "INFEASIBLE"

        space_usage, bay_allocation = self._summarise_space_usage(module_selection)

        return OptimizationResult(
            category_requirements=category_requirements,
            module_selection=module_selection,
            estimated_cost=total_cost,
            solver_status=str(status_name),
            space_usage=space_usage,
            bay_allocation=bay_allocation,
        )

    # ------------------------------------------------------------------
    def _build_greedy_selection(
        self, category_requirements: Dict[str, int]
    ) -> OptimizationResult:
        module_selection: Dict[str, int] = {}
        total_cost = 0.0

        for category, quantity in category_requirements.items():
            modules = sorted(
                self.repository.category_to_modules.get(category, []),
                key=lambda module: (
                    module.price if module.price > 0 else float("inf"),
                    module.block_count,
                    module.model_number,
                ),
            )
            if not modules:
                continue
            chosen = modules[0]
            module_selection[chosen.model_number] = quantity
            unit_cost = (
                chosen.price
                if chosen.price > 0
                else self.repository.category_prices.get(category, 1.0)
            )
            total_cost += unit_cost * quantity

        space_usage, bay_allocation = self._summarise_space_usage(module_selection)
        return OptimizationResult(
            category_requirements=category_requirements,
            module_selection=module_selection,
            estimated_cost=total_cost,
            solver_status="GREEDY",
            space_usage=space_usage,
            bay_allocation=bay_allocation,
        )

    # ------------------------------------------------------------------
    def optimise_panel(self, answers, boq) -> OptimizationResult:
        requirements = self.build_requirements(answers, boq)
        category_requirements = self.derive_category_requirements(requirements)

        solver_result = self._build_solver(category_requirements)
        if solver_result is None:
            solver_result = self._build_greedy_selection(category_requirements)

        manual_plan = self._derive_specific_modules(requirements)
        module_selection = dict(solver_result.module_selection)
        for model_number, quantity in manual_plan.items():
            module_selection[model_number] = max(module_selection.get(model_number, 0), quantity)

        enclosure_plan = self._derive_enclosure_modules(module_selection)
        for model_number, quantity in enclosure_plan.items():
            module_selection[model_number] = module_selection.get(model_number, 0) + quantity

        estimated_cost = sum(
            self.repository.estimate_cost(model_number, quantity)
            for model_number, quantity in module_selection.items()
        )
        space_usage, bay_allocation = self._summarise_space_usage(module_selection)

        solver_status = solver_result.solver_status or ""
        if solver_status:
            solver_status = f"{solver_status}+PLAN"
        else:
            solver_status = "PLAN"

        return OptimizationResult(
            category_requirements=category_requirements,
            module_selection=module_selection,
            estimated_cost=estimated_cost,
            solver_status=solver_status,
            space_usage=space_usage,
            bay_allocation=bay_allocation,
        )
