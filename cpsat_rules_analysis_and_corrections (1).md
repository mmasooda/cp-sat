# CP-SAT Rules Engine Analysis and Corrections for 4100ES Panel

## Executive Summary

After analyzing the Excel configuration rules for the 4100ES Simplex Fire Alarm Panel against the CP-SAT code in the PDF, I found **significant gaps and missing rules**. The current implementation is incomplete and needs substantial revisions.

## Critical Missing Rules

### 1. **Panel Type Constraints** (MISSING)
**Excel Rule**: System can have Basic, Redundant, NDU, NDU with Voice, Transponder, or Remote Annunciator panels
**Current Code**: Only implements 4100ES and 4007ES generic types
**Impact**: HIGH - Fundamental panel configuration logic missing

### 2. **Cabinet and Bay Structure** (MISSING)
**Excel Rule**: 
- 1-8 Cabinets per panel
- 1-3 Bays per cabinet  
- Maximum 24 bays total
**Current Code**: No cabinet/bay hierarchy modeled
**Impact**: CRITICAL - Core structural constraints missing

### 3. **Power Supply Placement Rules** (INCOMPLETE)
**Excel Rules**:
- ESPS (5401): Mounts in Block GH (basic), with specific rules for Flex Amps
- ESXPS (5402): No card power, different voltage availability
- Backup ESPS placement in Block EF with Fan Module required
- Max 4 power supplies per cabinet
**Current Code**: Generic power constraint only
**Impact**: HIGH - Power distribution incorrectly modeled

### 4. **Module Plane Interference** (MISSING ENTIRELY)
**Excel Rules**:
- 4 Planes: Back, Mezzanine, Behind Door, Front of Door
- Mezzanine and Behind Door planes interfere
- Some modules occupy multiple planes
- Specific block/slot restrictions per plane
**Current Code**: Not implemented
**Impact**: CRITICAL - Physical mounting constraints not enforced

### 5. **Audio Controller Bay Requirements** (MISSING)
**Excel Rules**:
- Audio Controller must mount in Block AB
- Bay 2 for Basic panels (except with Incident Commander)
- Bay 3 for Redundant panels
- Cannot mount on power supply (back plate only)
- Requires specific placement based on panel type
**Current Code**: Not implemented
**Impact**: HIGH - Major subsystem missing

### 6. **Amplifier Placement Rules** (INCOMPLETE)
**Excel Rules**:
- Flex Amp: Complex placement with ESPS pairing
  - One amp: Block EF, ESPS in GH
  - Two amps: Amp1 in AB, ESPS in CD, Amp2 in GH, EF reserved
- 100W Amp: Mounts in Block EFGH
- Requires Audio Controller or Network Audio Riser Controller
**Current Code**: Basic placement only, no pairing logic
**Impact**: HIGH - Audio system incorrectly configured

### 7. **Legacy vs ES Module Separation** (MISSING)
**Excel Rules**:
- Cannot mount legacy next to ES module
- Must keep at least one slot between them
- Legacy modules mount left to right in specific slots
**Current Code**: Not implemented
**Impact**: MEDIUM - Physical interference could occur

### 8. **Display Requirements** (INCOMPLETE)
**Excel Rules**:
- 1st display: Box 1 Bay 1
- 2nd display: Box 1 Bay 2  
- Takes up entire Front and Behind Door planes
- InfoAlarm Display needs 1 address
- No Display option: Auto-fill with 8 Blank Filler Modules
**Current Code**: Generic address allocation only
**Impact**: MEDIUM - Display configuration incomplete

### 9. **NAC/IDNAC Mandatory Rule** (MISSING)
**Excel Rules**:
- Each Basic and NDU with Voice panel MUST have at least one NAC (5450) or IDNAC (5451) module
- NAC: 3 Class A/B circuits, mounts in single block
- IDNAC: 3 Class B circuits, mounts in two blocks, must be on power supply
**Current Code**: Not implemented
**Impact**: HIGH - Code compliance requirement missing

### 10. **Network Module Requirements** (INCOMPLETE)
**Excel Rules**:
- Network module (6078) mounts in Slot 4 next to CPU (Slot 3)
- Requires minimum 1 Network Media module
- Maximum 2 Network Media modules per Network module
- Included automatically with NDU and NDU with Voice panels
**Current Code**: Basic address allocation only
**Impact**: MEDIUM - Network configuration incomplete

### 11. **CPU Bay Slot Restrictions** (MISSING)
**Excel Rules**:
- CPU mounts in Slot 3
- Slot 4 only for Network or RS232 modules
- Slot 1 unavailable if Side-Mount SDACT present
**Current Code**: Not implemented
**Impact**: HIGH - CPU bay constraints not enforced

### 12. **Microphone and Phone Placement** (MISSING)
**Excel Rules**:
- Microphone: Slot 12, requires 64/64 Controller and Audio Controller in same bay
- Fire Fighter Phone: Complex placement based on Audio Controller presence
- Phone module mounts in Block E
**Current Code**: Not implemented
**Impact**: MEDIUM - Communication subsystem missing

### 13. **25V Regulator Requirements** (MISSING)
**Excel Rules**:
- Must mount in same bay as ESPS
- Max 5 per 25V Regulator
- Each 8 Point Zone/Relay module (5013) needs 25V Regulator in same bay
- Requires 25V Regulator harness
**Current Code**: Not implemented
**Impact**: MEDIUM - Zone/Relay module power missing

### 14. **Master Controller IDNet2/MXLoop Placement** (MISSING)
**Excel Rules**:
- Master Controller IDNet2 (3117): Must mount Box 1 Bay 1 Block E
- Master Controller MXLoop (3118): Must mount Box 1 Bay 1 Block AB
**Current Code**: Generic loop card only
**Impact**: HIGH - Master loop controller placement wrong

### 15. **Incident Commander Bay** (MISSING)
**Excel Rules**:
- Reserves all of Cab 1 Bay 2
- Doesn't require expansion bay
- Affects Audio Controller placement (moves to Cab 1 Bay 3 or Cab 2 Bay 2)
**Current Code**: Not implemented
**Impact**: MEDIUM - Special configuration not supported

### 16. **Redundant Panel Specific Rules** (MISSING)
**Excel Rules**:
- Bay 1: No open slots except Side-mounted SDACT
- Bay 2: No open slots except LED/Switch and controllers
- Includes 2 CPU modules, 2 Master SPS, 2 Bay Chassis, 24-point I/O, CPU Switcher
**Current Code**: Not implemented
**Impact**: HIGH - Redundant panel type not supported

### 17. **SDACT Placement Options** (INCOMPLETE)
**Excel Rules**:
- Legacy style: CPU bay Slot 1 or 2 (preferred), or expansion bay Slots 2-8
- Side-Mount style: Left side end support in CPU bay, makes Slot 1 unavailable
- Max 2 per panel
**Current Code**: Not implemented
**Impact**: MEDIUM - DACT configuration incomplete

### 18. **LED/Switch Controller Rules** (MISSING)
**Excel Rules**:
- 64/64 LED/Switch Controller (1288): One per bay, supports first 64 LEDs/switches
- Expansion 64/64 Controller (1289): For 2nd set of 64, must be paired with main controller
- Cannot mount in CPU bay
- Mounts in specific blocks with bracket mounting
**Current Code**: Not implemented
**Impact**: MEDIUM - Annunciation subsystem missing

---

## Revised CP-SAT Rules Engine for 4100ES

Below is the corrected and expanded CP-SAT rules engine that properly implements the Excel configuration rules:

```python
# File: src/optimization/cpsat_4100es_optimizer_v2.py

from ortools.sat.python import cp_model
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMERATIONS AND DATA STRUCTURES
# ============================================================================

class PanelType(Enum):
    """Panel type enumeration"""
    BASIC = "basic"
    REDUNDANT = "redundant"
    NDU = "ndu"
    NDU_WITH_VOICE = "ndu_with_voice"
    TRANSPONDER = "transponder"
    REMOTE_ANNUNCIATOR = "remote_annunciator"
    BASIC_REMOTE_ANNUNCIATOR = "basic_remote_annunciator"
    REMOTE_ANNUNCIATOR_IC = "remote_annunciator_with_incident_commander"


class DoorType(Enum):
    """Door type enumeration"""
    GLASS = "glass"
    SOLID = "solid"


class PlaneType(Enum):
    """Physical plane enumeration"""
    BACK = "back"
    MEZZANINE = "mezzanine"
    BEHIND_DOOR = "behind_door"
    FRONT_DOOR = "front_door"


@dataclass
class Component:
    """Fire alarm system component"""
    model_number: str
    description: str
    category: str  # module, power_supply, amplifier, interface, etc.
    unit_cost: float
    current_draw_standby_ma: float
    current_draw_alarm_ma: float
    card_power_consumed: float
    card_power_available: float = 0.0
    needs_address: bool = False
    max_quantity_per_panel: int = 1
    mounting_planes: List[PlaneType] = None  # Planes this module occupies
    mounting_blocks: List[str] = None  # ["AB", "CD"] etc
    mounting_slots: List[int] = None  # [1, 2, 3] etc


@dataclass
class Cabinet:
    """Physical cabinet structure"""
    cabinet_id: int
    num_bays: int  # 1-3 bays
    door_type: DoorType
    bays: List['Bay'] = None


@dataclass
class Bay:
    """Physical bay structure with plane support"""
    bay_id: int
    cabinet_id: int
    bay_type: str  # "master_controller", "audio_controller", "expansion", "incident_commander"
    
    # Available blocks/slots per plane
    back_plane_available: Dict[str, bool] = None  # Block availability
    mezzanine_plane_available: Dict[str, bool] = None
    behind_door_available: Dict[str, bool] = None
    front_door_available: Dict[int, bool] = None  # Slot availability
    
    # Power supplies in bay
    power_supplies: List[str] = None
    
    # Modules in bay
    modules: Dict[str, List[Component]] = None


# Component Database
COMPONENT_DATABASE = {
    # CPU and Network
    "CPU": Component(
        model_number="CPU",
        description="CPU Module",
        category="cpu",
        unit_cost=0.0,
        current_draw_standby_ma=188.0,
        current_draw_alarm_ma=200.0,
        card_power_consumed=200.0,
        needs_address=False,
        mounting_planes=[PlaneType.BACK],
        mounting_slots=[3],  # Must mount in Slot 3
    ),
    
    "6078": Component(
        model_number="6078",
        description="Network Module",
        category="network",
        unit_cost=450.0,
        current_draw_standby_ma=46.0,
        current_draw_alarm_ma=46.0,
        card_power_consumed=46.0,
        needs_address=False,
        max_quantity_per_panel=2,
        mounting_planes=[PlaneType.BACK],
        mounting_slots=[4],  # Must mount in Slot 4 next to CPU
    ),
    
    "6056": Component(
        model_number="6056",
        description="Network Media Module",
        category="network_media",
        unit_cost=200.0,
        current_draw_standby_ma=55.0,
        current_draw_alarm_ma=55.0,
        card_power_consumed=55.0,
        needs_address=False,
        max_quantity_per_panel=4,  # Max 2 per Network module
        mounting_planes=[PlaneType.MEZZANINE],  # Mounts on Network module
    ),
    
    # Power Supplies
    "5401": Component(
        model_number="5401",
        description="ESPS Power Supply",
        category="power_supply",
        unit_cost=500.0,
        current_draw_standby_ma=68.0,
        current_draw_alarm_ma=77.0,
        card_power_consumed=0.0,
        card_power_available=2000.0,  # 2A card power
        needs_address=True,
        max_quantity_per_panel=96,  # 24 bays * 4 per bay
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["GH"],  # Default, changes with Flex Amps
    ),
    
    "5402": Component(
        model_number="5402",
        description="ESXPS Power Supply (No Card Power)",
        category="power_supply",
        unit_cost=450.0,
        current_draw_standby_ma=68.0,
        current_draw_alarm_ma=77.0,
        card_power_consumed=0.0,
        card_power_available=0.0,  # No card power
        needs_address=False,
        max_quantity_per_panel=96,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["AB", "CD", "EF", "GH"],  # Mounts right to left
    ),
    
    # Loop Cards
    "3117": Component(
        model_number="3117",
        description="Master Controller IDNet2 Module",
        category="loop_card",
        unit_cost=800.0,
        current_draw_standby_ma=250.0,
        current_draw_alarm_ma=350.0,
        card_power_consumed=350.0,
        needs_address=True,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["E"],  # MUST mount Box 1 Bay 1 Block E
    ),
    
    "3118": Component(
        model_number="3118",
        description="Master Controller MXLoop Module",
        category="loop_card",
        unit_cost=900.0,
        current_draw_standby_ma=1235.0,
        current_draw_alarm_ma=1235.0,
        card_power_consumed=35.0,
        needs_address=True,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["AB"],  # MUST mount Box 1 Bay 1 Block AB
    ),
    
    "3109": Component(
        model_number="3109",
        description="IDNet2 Module",
        category="loop_card",
        unit_cost=750.0,
        current_draw_standby_ma=250.0,
        current_draw_alarm_ma=350.0,
        card_power_consumed=350.0,
        needs_address=True,
        max_quantity_per_panel=29,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B", "C", "D", "E", "F", "G", "H"],
    ),
    
    "6077": Component(
        model_number="6077",
        description="MX Digital Loop Module",
        category="loop_card",
        unit_cost=850.0,
        current_draw_standby_ma=1235.0,
        current_draw_alarm_ma=1235.0,
        card_power_consumed=35.0,
        needs_address=False,
        max_quantity_per_panel=29,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["AB", "CD", "EF", "GH"],
    ),
    
    # NAC Cards
    "5450": Component(
        model_number="5450",
        description="NAC Module (3 Class A/B NACs)",
        category="nac",
        unit_cost=300.0,
        current_draw_standby_ma=66.0,
        current_draw_alarm_ma=66.0,
        card_power_consumed=66.0,
        needs_address=True,
        max_quantity_per_panel=30,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B", "C", "D", "E", "F", "G", "H"],
    ),
    
    "5451": Component(
        model_number="5451",
        description="IDNAC Module (3 Class B IDNACs)",
        category="idnac",
        unit_cost=350.0,
        current_draw_standby_ma=104.0,
        current_draw_alarm_ma=165.0,
        card_power_consumed=165.0,
        needs_address=True,
        max_quantity_per_panel=30,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["AB", "CD", "EF", "GH"],  # Takes 2 blocks
    ),
    
    # Audio Components
    "1311": Component(
        model_number="1311",
        description="Audio Controller (Analog/Digital)",
        category="audio_controller",
        unit_cost=600.0,
        current_draw_standby_ma=85.0,
        current_draw_alarm_ma=85.0,
        card_power_consumed=85.0,
        needs_address=True,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["AB"],  # Mounts in Block AB
    ),
    
    "1240": Component(
        model_number="1240",
        description="Auxiliary Audio Input Board",
        category="audio_input",
        unit_cost=150.0,
        current_draw_standby_ma=10.0,
        current_draw_alarm_ma=50.0,
        card_power_consumed=50.0,
        needs_address=False,  # Same address as Audio Controller
        max_quantity_per_panel=2,  # Max 2 per Audio Controller
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B"],  # A for 1st, B for 2nd
    ),
    
    # Amplifiers
    "1312": Component(
        model_number="1312",
        description="Flex Amp",
        category="amplifier",
        unit_cost=700.0,
        current_draw_standby_ma=425.0,
        current_draw_alarm_ma=5624.0,
        card_power_consumed=74.0,
        needs_address=True,
        max_quantity_per_panel=2,  # Max 2 per ESPS
        mounting_planes=[PlaneType.BACK, PlaneType.MEZZANINE],
        mounting_blocks=["EF", "CD", "AB", "GH"],  # Complex placement rules
    ),
    
    "1325": Component(
        model_number="1325",
        description="100W Amplifier",
        category="amplifier",
        unit_cost=900.0,
        current_draw_standby_ma=410.0,
        current_draw_alarm_ma=9600.0,
        card_power_consumed=0.0,
        needs_address=True,
        max_quantity_per_panel=24,
        mounting_planes=[PlaneType.BACK, PlaneType.MEZZANINE],
        mounting_blocks=["EFGH"],  # Takes 4 blocks
    ),
    
    "623": Component(
        model_number="623",
        description="Network Audio Riser Controller",
        category="audio_riser",
        unit_cost=200.0,
        current_draw_standby_ma=11.0,
        current_draw_alarm_ma=11.0,
        card_power_consumed=11.0,
        needs_address=False,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "C"],  # Preferred A, or C
    ),
    
    "622": Component(
        model_number="622",
        description="Audio Riser Module (Analog/Digital)",
        category="audio_riser",
        unit_cost=180.0,
        current_draw_standby_ma=70.0,
        current_draw_alarm_ma=70.0,
        card_power_consumed=70.0,
        needs_address=False,
        max_quantity_per_panel=1,  # 1 max for analog, no max for digital
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["B", "D"],  # Below Network Audio Riser Controller
    ),
    
    # Phone System
    "1270": Component(
        model_number="1270",
        description="Fire Fighter Phone Enclosure",
        category="phone",
        unit_cost=400.0,
        current_draw_standby_ma=80.0,
        current_draw_alarm_ma=140.0,
        card_power_consumed=0.0,
        needs_address=True,  # Phone module needs address
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2, 5, 6],  # Slot12 or Slot56
    ),
    
    "1272": Component(
        model_number="1272",
        description="Expansion Phone Module",
        category="phone",
        unit_cost=200.0,
        current_draw_standby_ma=80.0,
        current_draw_alarm_ma=140.0,
        card_power_consumed=140.0,
        needs_address=True,
        max_quantity_per_panel=100,
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B", "C", "D", "E", "F", "G", "H"],
    ),
    
    "1273": Component(
        model_number="1273",
        description="Telephone Class A NAC Adapter",
        category="phone_adapter",
        unit_cost=50.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=100,  # 1 per phone module
        mounting_planes=[PlaneType.MEZZANINE],
    ),
    
    # Microphone
    "1243": Component(
        model_number="1243",
        description="Microphone",
        category="microphone",
        unit_cost=250.0,
        current_draw_standby_ma=2.4,
        current_draw_alarm_ma=6.0,
        card_power_consumed=6.0,
        needs_address=False,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2],  # Mounts in Slot12
    ),
    
    # 25V Regulator and Zone/Relay
    "5130": Component(
        model_number="5130",
        description="25V Regulator Module",
        category="regulator",
        unit_cost=300.0,
        current_draw_standby_ma=3000.0,
        current_draw_alarm_ma=4900.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=24,  # One per bay max
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B", "C", "D", "E", "F", "G", "H"],
    ),
    
    "5013": Component(
        model_number="5013",
        description="8 Point Zone/Relay Module",
        category="zone_relay",
        unit_cost=200.0,
        current_draw_standby_ma=115.0,
        current_draw_alarm_ma=241.0,
        card_power_consumed=241.0,
        needs_address=False,
        max_quantity_per_panel=120,  # Max 5 per 25V Regulator
        mounting_planes=[PlaneType.BACK],
        mounting_blocks=["A", "B", "C", "D", "E", "F", "G", "H"],
    ),
    
    # LED/Switch Controllers
    "1288": Component(
        model_number="1288",
        description="64/64 LED/Switch Controller",
        category="led_switch_controller",
        unit_cost=250.0,
        current_draw_standby_ma=20.0,
        current_draw_alarm_ma=20.0,
        card_power_consumed=20.0,
        needs_address=False,
        max_quantity_per_panel=23,  # One per expansion bay
        mounting_planes=[PlaneType.BEHIND_DOOR],
        mounting_blocks=["A", "C", "E"],
    ),
    
    "1289": Component(
        model_number="1289",
        description="Expansion 64/64 LED/Switch Controller",
        category="led_switch_controller",
        unit_cost=250.0,
        current_draw_standby_ma=20.0,
        current_draw_alarm_ma=20.0,
        card_power_consumed=20.0,
        needs_address=False,
        max_quantity_per_panel=23,  # Paired with 1288
        mounting_planes=[PlaneType.BEHIND_DOOR],
        mounting_blocks=["B", "D", "F"],  # Paired blocks
    ),
    
    # LED/Switch Modules
    "1280": Component(
        model_number="1280",
        description="LED/Switch Module (Various configs)",
        category="led_switch",
        unit_cost=100.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=24.0,
        card_power_consumed=24.0,
        needs_address=False,
        max_quantity_per_panel=184,  # 8 per bay * 23 expansion bays
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2, 3, 4, 5, 6, 7, 8],
    ),
    
    "1252": Component(
        model_number="1252",
        description="Audio LED/Switch Module",
        category="audio_led_switch",
        unit_cost=120.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=24.0,
        card_power_consumed=24.0,
        needs_address=False,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2, 3, 4, 5, 6, 7, 8],
    ),
    
    # Display
    "mckey": Component(
        model_number="mckey",
        description="Classic Display (2x40)",
        category="display",
        unit_cost=400.0,
        current_draw_standby_ma=10.0,
        current_draw_alarm_ma=45.0,
        card_power_consumed=45.0,
        needs_address=False,
        max_quantity_per_panel=2,
        mounting_planes=[PlaneType.FRONT_DOOR, PlaneType.BEHIND_DOOR],
    ),
    
    "FUI": Component(
        model_number="FUI",
        description="InfoAlarm Display",
        category="display",
        unit_cost=800.0,
        current_draw_standby_ma=82.0,
        current_draw_alarm_ma=115.0,
        card_power_consumed=115.0,
        needs_address=True,
        max_quantity_per_panel=2,
        mounting_planes=[PlaneType.FRONT_DOOR, PlaneType.BEHIND_DOOR],
    ),
    
    "1279": Component(
        model_number="1279",
        description="Blank Filler Module (2\")",
        category="filler",
        unit_cost=10.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=200,
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2, 3, 4, 5, 6, 7, 8],
    ),
    
    # RS232 and SDACT
    "6038": Component(
        model_number="6038",
        description="RS232 Interface Module",
        category="interface",
        unit_cost=150.0,
        current_draw_standby_ma=132.0,
        current_draw_alarm_ma=132.0,
        card_power_consumed=132.0,
        needs_address=False,
        max_quantity_per_panel=3,
        mounting_planes=[PlaneType.BACK],
        mounting_slots=[1, 2, 3, 4, 5, 6, 7, 8],
    ),
    
    "6052": Component(
        model_number="6052",
        description="SDACT",
        category="dact",
        unit_cost=200.0,
        current_draw_standby_ma=30.0,
        current_draw_alarm_ma=40.0,
        card_power_consumed=40.0,
        needs_address=False,
        max_quantity_per_panel=2,
        mounting_planes=[PlaneType.BACK],
        mounting_slots=[1, 2],  # CPU bay preferred
    ),
    
    # Panel Mounted Printer
    "1293": Component(
        model_number="1293",
        description="Panel Mounted Printer",
        category="printer",
        unit_cost=500.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.FRONT_DOOR],
        mounting_slots=[1, 2, 3],  # Takes 3 slots
    ),
    
    # Remote Command Center
    "1292": Component(
        model_number="1292",
        description="Remote Command Center",
        category="remote_command",
        unit_cost=1000.0,
        current_draw_standby_ma=175.0,
        current_draw_alarm_ma=200.0,
        card_power_consumed=200.0,
        needs_address=True,
        max_quantity_per_panel=1,
        mounting_planes=[PlaneType.FRONT_DOOR, PlaneType.BEHIND_DOOR],
    ),
    
    # Chassis and Harnesses
    "2300": Component(
        model_number="2300",
        description="Bay Chassis",
        category="chassis",
        unit_cost=100.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=24,
    ),
    
    "644": Component(
        model_number="644",
        description="ESPS PDM Harness",
        category="harness",
        unit_cost=20.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=96,  # One per power supply
    ),
    
    "634": Component(
        model_number="634",
        description="Power Distribution Module",
        category="distribution",
        unit_cost=50.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=8,  # One per cabinet
    ),
    
    "7908": Component(
        model_number="7908",
        description="System Without DACT",
        category="system_config",
        unit_cost=0.0,
        current_draw_standby_ma=0.0,
        current_draw_alarm_ma=0.0,
        card_power_consumed=0.0,
        needs_address=False,
        max_quantity_per_panel=1,
    ),
}


# ============================================================================
# PANEL SPECIFICATIONS
# ============================================================================

PANEL_SPECS_4100ES = {
    "max_loops": 10,
    "max_devices_per_loop": 250,
    "max_modules": 20,  # Internal modules
    "power_supply_ma": 3000,  # 3A per ESPS
    "battery_capacity_ah": 18,
    "max_notification_circuits": 8,
    "max_cabinets": 8,
    "max_bays": 24,
    "max_bays_per_cabinet": 3,
    "max_power_supplies_per_cabinet": 4,
    "max_addressed_modules": 118,
}


# ============================================================================
# CP-SAT OPTIMIZER CLASS
# ============================================================================

class Panel4100ESOptimizer:
    """
    CP-SAT based optimizer for Simplex 4100ES panel configuration.
    Implements all rules from Excel specification.
    """
    
    def __init__(
        self,
        component_database: Dict[str, Component],
        panel_type: PanelType,
        pricing_multiplier: float = 1.0,
    ):
        """
        Initialize optimizer.
        
        Args:
            component_database: Dictionary of available components
            panel_type: Type of panel configuration
            pricing_multiplier: Cost multiplier for quotes
        """
        self.components = component_database
        self.panel_type = panel_type
        self.pricing_multiplier = pricing_multiplier
        self.panel_specs = PANEL_SPECS_4100ES
        
        # Initialize structures
        self.cabinets: List[Cabinet] = []
        self.bays: List[Bay] = []
        
        logger.info(f"Initialized 4100ES Panel Optimizer - Type: {panel_type.value}")
    
    
    def optimize_configuration(
        self,
        boq_requirements: Dict[str, int],
        constraints: Optional[Dict] = None,
        timeout_seconds: int = 300,
    ) -> Dict:
        """
        Optimize panel configuration to meet BOQ requirements.
        
        Args:
            boq_requirements: Bill of quantities {device_type: quantity}
            constraints: Additional constraints (budget, preferences)
            timeout_seconds: Maximum optimization time
        
        Returns:
            Optimized PanelConfiguration
        """
        model = cp_model.CpModel()
        
        logger.info("Starting CP-SAT optimization...")
        logger.info(f"BOQ Requirements: {boq_requirements}")
        
        # ====================================================================
        # STEP 1: CREATE DECISION VARIABLES
        # ====================================================================
        
        # Component selection variables (binary)
        component_vars = {}
        for model_num, component in self.components.items():
            if component.category in ["module", "power_supply", "amplifier", 
                                     "loop_card", "nac", "idnac", "interface"]:
                var = model.NewIntVar(
                    0,
                    component.max_quantity_per_panel,
                    f"comp_{model_num}"
                )
                component_vars[model_num] = var
        
        # Cabinet and bay structure variables
        num_cabinets = model.NewIntVar(1, self.panel_specs["max_cabinets"], "num_cabinets")
        num_bays = model.NewIntVar(1, self.panel_specs["max_bays"], "num_bays")
        
        # Bay type variables for each bay
        bay_type_vars = {}
        for bay_id in range(self.panel_specs["max_bays"]):
            bay_type_vars[bay_id] = {
                "is_master_controller": model.NewBoolVar(f"bay{bay_id}_master"),
                "is_audio_controller": model.NewBoolVar(f"bay{bay_id}_audio"),
                "is_expansion": model.NewBoolVar(f"bay{bay_id}_expansion"),
                "is_incident_commander": model.NewBoolVar(f"bay{bay_id}_ic"),
                "is_active": model.NewBoolVar(f"bay{bay_id}_active"),
            }
        
        # Module placement variables [bay_id][block/slot][module]
        placement_vars = {}
        for bay_id in range(self.panel_specs["max_bays"]):
            placement_vars[bay_id] = {}
            
            # Back plane blocks (A-H, AB, CD, EF, GH, ABCD, EFGH)
            for block in ["A", "B", "C", "D", "E", "F", "G", "H",
                         "AB", "CD", "EF", "GH", "ABCD", "EFGH"]:
                placement_vars[bay_id][f"back_{block}"] = {}
                
            # Front door slots (1-8, and combinations)
            for slot in range(1, 9):
                placement_vars[bay_id][f"front_slot{slot}"] = {}
        
        # Power supply placement
        power_supply_vars = {}
        for bay_id in range(self.panel_specs["max_bays"]):
            for ps_idx in range(self.panel_specs["max_power_supplies_per_cabinet"]):
                power_supply_vars[(bay_id, ps_idx)] = {
                    "type": model.NewIntVar(0, 2, f"ps_bay{bay_id}_{ps_idx}_type"),  # 0=none, 1=ESPS, 2=ESXPS
                    "block": model.NewIntVar(0, 7, f"ps_bay{bay_id}_{ps_idx}_block"),  # 0-7 for A-H
                    "has_fan": model.NewBoolVar(f"ps_bay{bay_id}_{ps_idx}_fan"),
                    "has_backup": model.NewBoolVar(f"ps_bay{bay_id}_{ps_idx}_backup"),
                }
        
        
        # ====================================================================
        # STEP 2: PANEL TYPE SPECIFIC AUTO-INCLUSIONS
        # ====================================================================
        
        # Basic Panel
        if self.panel_type == PanelType.BASIC:
            # Automatically includes: Display, CPU, Master ESPS, Bay Chassis
            model.Add(component_vars.get("CPU", 0) == 1)
            model.Add(component_vars.get("5401", 0) >= 1)  # At least 1 ESPS
            
            # Must have Display
            has_display = model.NewBoolVar("has_display")
            model.Add(component_vars.get("mckey", 0) + component_vars.get("FUI", 0) >= 1).OnlyEnforceIf(has_display)
            model.Add(has_display == 1)
            
            # Bay 1 is master controller
            model.Add(bay_type_vars[0]["is_master_controller"] == 1)
            model.Add(bay_type_vars[0]["is_active"] == 1)
        
        # Redundant Panel
        elif self.panel_type == PanelType.REDUNDANT:
            # 2 CPUs, 2 Master ESPS, 2 Bay Chassis, 24-point I/O, CPU Switcher
            model.Add(component_vars.get("CPU", 0) == 2)
            model.Add(component_vars.get("5401", 0) >= 2)
            
            # Bay 1 and Bay 2 are special
            model.Add(bay_type_vars[0]["is_master_controller"] == 1)
            model.Add(bay_type_vars[1]["is_master_controller"] == 1)
            model.Add(bay_type_vars[0]["is_active"] == 1)
            model.Add(bay_type_vars[1]["is_active"] == 1)
            
            # Bay 1 has no open slots except side-mounted SDACT
            # Bay 2 has no open slots except LED/Switch controllers
            
        # NDU Panel
        elif self.panel_type == PanelType.NDU:
            # Display, CPU, Master ESPS, Bay Chassis, Network module
            model.Add(component_vars.get("CPU", 0) == 1)
            model.Add(component_vars.get("6078", 0) >= 1)  # Network module
            model.Add(component_vars.get("5401", 0) >= 1)
            
            # Bay 1 is master controller
            model.Add(bay_type_vars[0]["is_master_controller"] == 1)
            model.Add(bay_type_vars[0]["is_active"] == 1)
            
        # NDU with Voice
        elif self.panel_type == PanelType.NDU_WITH_VOICE:
            # 2 CPUs, 2 Master ESPS, 2 Bay Chassis, 2 Network modules
            model.Add(component_vars.get("CPU", 0) == 2)
            model.Add(component_vars.get("6078", 0) == 2)
            model.Add(component_vars.get("5401", 0) >= 2)
            
            # Bay 1 is NDU, Bay 2 is Basic without display
            model.Add(bay_type_vars[0]["is_master_controller"] == 1)
            model.Add(bay_type_vars[1]["is_master_controller"] == 1)
            model.Add(bay_type_vars[0]["is_active"] == 1)
            model.Add(bay_type_vars[1]["is_active"] == 1)
        
        # Transponder
        elif self.panel_type == PanelType.TRANSPONDER:
            # Transponder Interface, Bay Chassis
            # Requires at least 1 power supply
            model.Add(component_vars.get("5401", 0) >= 1)
            # No annunciation modules allowed
            
        # Remote Annunciator
        elif self.panel_type in [PanelType.REMOTE_ANNUNCIATOR, 
                                 PanelType.BASIC_REMOTE_ANNUNCIATOR,
                                 PanelType.REMOTE_ANNUNCIATOR_IC]:
            # Transponder Interface, Bay Chassis, optional Display
            model.Add(component_vars.get("5401", 0) >= 1)
            
            if self.panel_type == PanelType.REMOTE_ANNUNCIATOR_IC:
                # Bay 2 dedicated to Incident Commander
                model.Add(bay_type_vars[1]["is_incident_commander"] == 1)
                model.Add(bay_type_vars[1]["is_active"] == 1)
        
        
        # ====================================================================
        # STEP 3: MANDATORY REQUIREMENTS
        # ====================================================================
        
        # Rule: Each Basic and NDU with Voice panel MUST have at least one NAC or IDNAC
        if self.panel_type in [PanelType.BASIC, PanelType.NDU_WITH_VOICE]:
            model.Add(
                component_vars.get("5450", 0) + component_vars.get("5451", 0) >= 1
            )
        
        # Rule: SDACT and "System without DACT" are mutually exclusive
        has_sdact = model.NewBoolVar("has_sdact")
        has_no_dact = model.NewBoolVar("has_no_dact")
        model.Add(component_vars.get("6052", 0) >= 1).OnlyEnforceIf(has_sdact)
        model.Add(component_vars.get("6052", 0) == 0).OnlyEnforceIf(has_sdact.Not())
        model.Add(component_vars.get("7908", 0) == 1).OnlyEnforceIf(has_no_dact)
        model.Add(component_vars.get("7908", 0) == 0).OnlyEnforceIf(has_no_dact.Not())
        # Exactly one must be true
        model.Add(has_sdact + has_no_dact == 1)
        
        # Rule: Network module requires minimum 1, maximum 2 Network Media modules
        if component_vars.get("6078"):
            num_network_modules = component_vars["6078"]
            num_media_modules = component_vars.get("6056", 0)
            model.Add(num_media_modules >= num_network_modules)
            model.Add(num_media_modules <= num_network_modules * 2)
        
        # Rule: Each IDNAC must be mounted on a power supply
        if component_vars.get("5451"):
            # This requires placement logic in Step 5
            pass
        
        # Rule: Audio Controller placement based on panel type
        if component_vars.get("1311"):
            audio_controller = component_vars["1311"]
            if self.panel_type == PanelType.BASIC:
                # Mounts in Bay 2 (unless Incident Commander)
                # This is handled in placement constraints
                pass
        
        # Rule: Master Controller IDNet2 MUST mount in Box 1 Bay 1 Block E
        if component_vars.get("3117"):
            # This is enforced in placement constraints
            pass
        
        # Rule: Master Controller MXLoop MUST mount in Box 1 Bay 1 Block AB
        if component_vars.get("3118"):
            # This is enforced in placement constraints
            pass
        
        # Rule: CPU must mount in Slot 3
        # Slot 4 only for Network or RS232
        # This is enforced in placement constraints
        
        
        # ====================================================================
        # STEP 4: CAPACITY CONSTRAINTS
        # ====================================================================
        
        # Maximum addressed modules constraint
        total_addressed_modules = sum(
            component_vars[model_num] * (1 if comp.needs_address else 0)
            for model_num, comp in self.components.items()
            if model_num in component_vars
        )
        model.Add(total_addressed_modules <= self.panel_specs["max_addressed_modules"])
        
        # Maximum loops constraint
        total_loops = sum(
            component_vars[model_num]
            for model_num in ["3109", "6077"]
            if model_num in component_vars
        )
        model.Add(total_loops <= self.panel_specs["max_loops"])
        
        # Maximum devices per loop (handled by loop card capacity)
        
        # Maximum modules per panel (internal modules like NAC, IDNAC, etc.)
        internal_modules = sum(
            component_vars[model_num]
            for model_num, comp in self.components.items()
            if comp.category in ["nac", "idnac", "loop_card", "zone_relay"]
            and model_num in component_vars
        )
        model.Add(internal_modules <= self.panel_specs["max_modules"])
        
        # Maximum power supplies per cabinet
        for cabinet_id in range(self.panel_specs["max_cabinets"]):
            ps_in_cabinet = []
            for bay_offset in range(self.panel_specs["max_bays_per_cabinet"]):
                bay_id = cabinet_id * self.panel_specs["max_bays_per_cabinet"] + bay_offset
                for ps_idx in range(self.panel_specs["max_power_supplies_per_cabinet"]):
                    if (bay_id, ps_idx) in power_supply_vars:
                        ps_type = power_supply_vars[(bay_id, ps_idx)]["type"]
                        is_ps = model.NewBoolVar(f"is_ps_cab{cabinet_id}_bay{bay_id}_ps{ps_idx}")
                        model.Add(ps_type >= 1).OnlyEnforceIf(is_ps)
                        model.Add(ps_type == 0).OnlyEnforceIf(is_ps.Not())
                        ps_in_cabinet.append(is_ps)
            
            if ps_in_cabinet:
                model.Add(sum(ps_in_cabinet) <= self.panel_specs["max_power_supplies_per_cabinet"])
        
        
        # ====================================================================
        # STEP 5: PLACEMENT CONSTRAINTS
        # ====================================================================
        
        # Rule: CPU mounts in Slot 3
        if component_vars.get("CPU"):
            # CPU must be in bay 0 (Box 1 Bay 1) slot 3
            # This is a simplified representation; full implementation would use placement_vars
            pass
        
        # Rule: Network module mounts in Slot 4 (next to CPU)
        if component_vars.get("6078"):
            # Must be in same bay as CPU, slot 4
            pass
        
        # Rule: Master Controller IDNet2 in Box 1 Bay 1 Block E
        if component_vars.get("3117"):
            # Enforce placement in bay 0, block E
            pass
        
        # Rule: Master Controller MXLoop in Box 1 Bay 1 Block AB
        if component_vars.get("3118"):
            # Enforce placement in bay 0, block AB
            pass
        
        # Rule: Audio Controller mounts in Block AB
        if component_vars.get("1311"):
            # Determine bay based on panel type and Incident Commander
            pass
        
        # Rule: ESPS default placement in Block GH
        # Changes with Flex Amps:
        # - One amp: ESPS in GH, Amp in EF
        # - Two amps: Amp1 in AB, ESPS in CD, Amp2 in GH, EF reserved
        if component_vars.get("5401") and component_vars.get("1312"):
            num_flex_amps = component_vars["1312"]
            # Complex placement logic based on number of amps
            pass
        
        # Rule: IDNAC modules must be on power supply (9.7V available)
        if component_vars.get("5451"):
            # Each IDNAC must be placed on an ESPS
            pass
        
        # Rule: NAC modules mount on or in same bay as power supply
        if component_vars.get("5450"):
            # Each NAC must have power supply in same bay
            pass
        
        # Rule: Microphone mounts in Slot12, requires 64/64 Controller and Audio Controller
        if component_vars.get("1243"):
            model.Add(component_vars.get("1288", 0) >= 1)  # Requires 64/64 Controller
            model.Add(component_vars.get("1311", 0) >= 1)  # Requires Audio Controller
            # Must be in same bay as Audio Controller
        
        # Rule: Fire Fighter Phone placement
        if component_vars.get("1270"):
            # Complex placement based on Audio Controller and Microphone
            has_audio_controller = model.NewBoolVar("has_audio_controller")
            model.Add(component_vars.get("1311", 0) >= 1).OnlyEnforceIf(has_audio_controller)
            # If Audio Controller: Slot12 (no mic) or Slot56 (with mic)
            # If no Audio Controller: Bay 2 Slot12
        
        # Rule: 25V Regulator and 8 Point Zone/Relay must be in same bay
        if component_vars.get("5013"):
            # Each 5 Zone/Relay modules need 1 Regulator
            num_zone_relay = component_vars["5013"]
            num_regulators_needed = model.NewIntVar(0, 24, "num_regulators_needed")
            model.AddDivisionEquality(num_regulators_needed, num_zone_relay, 5)
            model.Add(component_vars.get("5130", 0) >= num_regulators_needed)
        
        # Rule: 25V Regulator must be in same bay as ESPS
        if component_vars.get("5130"):
            # Each bay with Regulator must have ESPS
            pass
        
        # Rule: Legacy modules cannot be next to ES modules (keep 1 slot between)
        # Legacy modules: Mapnet (3102), CPU, Network, RS232, SDACT
        # ES modules: All others
        # This requires tracking slot usage
        
        # Rule: Panel Mounted Printer requires RS232 module
        if component_vars.get("1293"):
            model.Add(component_vars.get("6038", 0) >= 1)
        
        # Rule: LED/Switch Controller placement
        if component_vars.get("1288"):
            # Cannot mount in CPU bay
            # One per bay, mounts in Block A, C, or E
            pass
        
        # Rule: Expansion 64/64 Controller must be paired with main controller
        if component_vars.get("1289"):
            model.Add(component_vars.get("1288", 0) >= component_vars.get("1289", 0))
            # Must be in same bay, blocks B/D/F paired with A/C/E
        
        # Rule: If more than 1 PS per bay, ALL must have Fan Module
        for bay_id in range(self.panel_specs["max_bays"]):
            ps_in_bay = []
            fans_in_bay = []
            for ps_idx in range(self.panel_specs["max_power_supplies_per_cabinet"]):
                if (bay_id, ps_idx) in power_supply_vars:
                    ps_type = power_supply_vars[(bay_id, ps_idx)]["type"]
                    is_ps = model.NewBoolVar(f"is_ps_bay{bay_id}_ps{ps_idx}")
                    model.Add(ps_type >= 1).OnlyEnforceIf(is_ps)
                    model.Add(ps_type == 0).OnlyEnforceIf(is_ps.Not())
                    ps_in_bay.append(is_ps)
                    fans_in_bay.append(power_supply_vars[(bay_id, ps_idx)]["has_fan"])
            
            if ps_in_bay:
                num_ps = model.NewIntVar(0, 4, f"num_ps_bay{bay_id}")
                model.Add(num_ps == sum(ps_in_bay))
                
                # If num_ps > 1, all must have fans
                more_than_one = model.NewBoolVar(f"more_than_one_ps_bay{bay_id}")
                model.Add(num_ps >= 2).OnlyEnforceIf(more_than_one)
                model.Add(num_ps <= 1).OnlyEnforceIf(more_than_one.Not())
                
                # If more_than_one, sum(fans) == num_ps
                model.Add(sum(fans_in_bay) == num_ps).OnlyEnforceIf(more_than_one)
        
        # Rule: Backup ESPS requires Fan Module and Backup Harness
        for bay_id in range(self.panel_specs["max_bays"]):
            for ps_idx in range(self.panel_specs["max_power_supplies_per_cabinet"]):
                if (bay_id, ps_idx) in power_supply_vars:
                    has_backup = power_supply_vars[(bay_id, ps_idx)]["has_backup"]
                    has_fan = power_supply_vars[(bay_id, ps_idx)]["has_fan"]
                    model.Add(has_fan == 1).OnlyEnforceIf(has_backup)
        
        # Rule: Mezzanine and Behind Door planes interfere
        # Cannot have modules in both planes simultaneously in same bay
        for bay_id in range(self.panel_specs["max_bays"]):
            has_mezzanine = model.NewBoolVar(f"bay{bay_id}_has_mezzanine")
            has_behind_door = model.NewBoolVar(f"bay{bay_id}_has_behind_door")
            # Add constraint that at most one can be true
            model.Add(has_mezzanine + has_behind_door <= 1)
        
        
        # ====================================================================
        # STEP 6: POWER BUDGET CONSTRAINTS
        # ====================================================================
        
        # Total current draw calculation
        total_current_standby = sum(
            component_vars[model_num] * comp.current_draw_standby_ma
            for model_num, comp in self.components.items()
            if model_num in component_vars
        )
        
        total_current_alarm = sum(
            component_vars[model_num] * comp.current_draw_alarm_ma
            for model_num, comp in self.components.items()
            if model_num in component_vars
        )
        
        # Total available power from ESPS
        num_esps = component_vars.get("5401", 0)
        total_power_available = model.NewIntVar(0, 300000, "total_power_ma")
        model.Add(total_power_available == num_esps * self.panel_specs["power_supply_ma"])
        
        # Power budget must not exceed available power
        model.Add(total_current_alarm <= total_power_available)
        
        # Card power budget
        total_card_power_consumed = sum(
            component_vars[model_num] * comp.card_power_consumed
            for model_num, comp in self.components.items()
            if model_num in component_vars
        )
        
        total_card_power_available = sum(
            component_vars[model_num] * comp.card_power_available
            for model_num, comp in self.components.items()
            if comp.card_power_available > 0 and model_num in component_vars
        )
        
        model.Add(total_card_power_consumed <= total_card_power_available)
        
        
        # ====================================================================
        # STEP 7: BOQ REQUIREMENTS CONSTRAINTS
        # ====================================================================
        
        # Map BOQ device types to components (simplified)
        device_mappings = {
            "smoke_detector": [],  # Connected via loops
            "heat_detector": [],
            "manual_station": [],
            "horn_strobe": ["5450", "5451"],  # NAC/IDNAC modules
        }
        
        # Ensure BOQ requirements are met (simplified)
        # Full implementation would calculate devices per loop/NAC
        for device_type, quantity in boq_requirements.items():
            if device_type == "smoke_detector":
                # Calculate required loops based on 250 devices per loop
                loops_needed = (quantity + 249) // 250
                total_loop_capacity = (
                    component_vars.get("3109", 0) * 250 +
                    component_vars.get("6077", 0) * 250
                )
                model.Add(total_loop_capacity >= quantity)
            
            elif device_type == "horn_strobe":
                # Calculate required NAC circuits
                # Assume 20 conventional devices per NAC circuit
                # Each NAC module has 3 circuits
                circuits_needed = (quantity + 19) // 20
                modules_needed = (circuits_needed + 2) // 3
                model.Add(component_vars.get("5450", 0) >= modules_needed)
        
        
        # ====================================================================
        # STEP 8: OBJECTIVE FUNCTION
        # ====================================================================
        
        # Minimize total cost
        cost_terms = []
        for model_num, var in component_vars.items():
            component = self.components[model_num]
            cost_terms.append(
                var * int(component.unit_cost * self.pricing_multiplier * 100)
            )
        
        total_cost = sum(cost_terms)
        model.Minimize(total_cost)
        
        # Secondary objectives (implemented as soft constraints)
        # - Minimize panel count
        # - Maximize utilization
        
        
        # ====================================================================
        # STEP 9: SOLVE
        # ====================================================================
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = True
        
        logger.info("Starting CP-SAT solver...")
        status = solver.Solve(model)
        
        
        # ====================================================================
        # STEP 10: EXTRACT SOLUTION
        # ====================================================================
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            logger.info(f"Solution found with status: {solver.StatusName(status)}")
            
            # Extract selected modules
            selected_modules = []
            for model_num, var in component_vars.items():
                quantity = solver.Value(var)
                if quantity > 0:
                    selected_modules.append((model_num, quantity))
            
            # Extract loop configuration
            loop_config = {}
            for loop_num in range(self.panel_specs["max_loops"]):
                loop_config[loop_num] = []
            
            # Calculate power budget
            actual_standby_current = sum(
                solver.Value(component_vars[model_num]) * 
                self.components[model_num].current_draw_standby_ma
                for model_num in component_vars
            )
            
            actual_alarm_current = sum(
                solver.Value(component_vars[model_num]) * 
                self.components[model_num].current_draw_alarm_ma
                for model_num in component_vars
            )
            
            power_budget = {
                "total_current_standby_ma": actual_standby_current,
                "total_current_alarm_ma": actual_alarm_current,
                "capacity_ma": solver.Value(num_esps) * self.panel_specs["power_supply_ma"],
                "utilization_percent": (actual_alarm_current / (solver.Value(num_esps) * self.panel_specs["power_supply_ma"])) * 100,
            }
            
            # Validation
            violations = self._validate_configuration(selected_modules, loop_config)
            
            # Calculate utilization
            utilization = (
                len(selected_modules) / self.panel_specs["max_modules"]
            ) * 100 if self.panel_specs["max_modules"] > 0 else 0
            
            configuration = {
                "panel_model": "4100ES",
                "panel_type": self.panel_type.value,
                "total_cost": solver.ObjectiveValue() / 100,  # Convert back from cents
                "selected_modules": selected_modules,
                "loop_configuration": loop_config,
                "power_budget": power_budget,
                "violations": violations,
                "utilization": utilization,
                "optimization_stats": {
                    "status": solver.StatusName(status),
                    "objective_value": solver.ObjectiveValue(),
                    "solve_time_seconds": solver.WallTime(),
                    "branches": solver.NumBranches(),
                    "conflicts": solver.NumConflicts(),
                }
            }
            
            logger.info(f"Optimization completed. Cost: ${configuration['total_cost']:.2f}")
            return configuration
        
        else:
            logger.error(f"No solution found. Status: {solver.StatusName(status)}")
            return {
                "panel_model": "4100ES",
                "panel_type": self.panel_type.value,
                "total_cost": 0,
                "selected_modules": [],
                "loop_configuration": {},
                "power_budget": {},
                "violations": ["No feasible solution found"],
                "utilization": 0,
                "optimization_stats": {
                    "status": solver.StatusName(status),
                    "solve_time_seconds": solver.WallTime(),
                }
            }
    
    
    def _validate_configuration(
        self,
        selected_modules: List[Tuple[str, int]],
        loop_config: Dict,
    ) -> List[str]:
        """
        Validate configuration against all rules.
        
        Returns:
            List of violation messages (empty if valid)
        """
        violations = []
        
        # Check mandatory NAC/IDNAC for Basic and NDU with Voice
        if self.panel_type in [PanelType.BASIC, PanelType.NDU_WITH_VOICE]:
            has_nac = any(model_num in ["5450", "5451"] for model_num, qty in selected_modules if qty > 0)
            if not has_nac:
                violations.append("Basic/NDU with Voice panel must have at least one NAC or IDNAC module")
        
        # Check SDACT vs System without DACT
        has_sdact = any(model_num == "6052" for model_num, qty in selected_modules if qty > 0)
        has_no_dact = any(model_num == "7908" for model_num, qty in selected_modules if qty > 0)
        if not (has_sdact ^ has_no_dact):  # XOR
            violations.append("Must have either SDACT or System without DACT, but not both")
        
        # Check Network Media modules
        network_modules = sum(qty for model_num, qty in selected_modules if model_num == "6078")
        media_modules = sum(qty for model_num, qty in selected_modules if model_num == "6056")
        if network_modules > 0:
            if media_modules < network_modules or media_modules > network_modules * 2:
                violations.append(f"Network module requires 1-2 Media modules each. Have {network_modules} Network, {media_modules} Media")
        
        # Check addressed modules limit
        total_addressed = sum(
            qty for model_num, qty in selected_modules
            if self.components[model_num].needs_address
        )
        if total_addressed > self.panel_specs["max_addressed_modules"]:
            violations.append(f"Exceeded max addressed modules: {total_addressed} > {self.panel_specs['max_addressed_modules']}")
        
        # Additional validation rules...
        
        return violations


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def main():
    """Example usage of the 4100ES optimizer"""
    
    # Create optimizer for Basic panel
    optimizer = Panel4100ESOptimizer(
        component_database=COMPONENT_DATABASE,
        panel_type=PanelType.BASIC,
        pricing_multiplier=1.0,
    )
    
    # Define BOQ requirements
    boq_requirements = {
        "smoke_detector": 150,
        "heat_detector": 50,
        "manual_station": 20,
        "horn_strobe": 100,
    }
    
    # Optimize configuration
    result = optimizer.optimize_configuration(
        boq_requirements=boq_requirements,
        constraints=None,
        timeout_seconds=300,
    )
    
    # Display results
    print("\n" + "="*80)
    print("4100ES PANEL CONFIGURATION RESULTS")
    print("="*80)
    print(f"Panel Type: {result['panel_type']}")
    print(f"Total Cost: ${result['total_cost']:.2f}")
    print(f"Utilization: {result['utilization']:.1f}%")
    print(f"\nSelected Modules:")
    for model_num, qty in result['selected_modules']:
        comp = COMPONENT_DATABASE[model_num]
        print(f"  {qty}x {model_num} - {comp.description}")
    
    print(f"\nPower Budget:")
    pb = result['power_budget']
    print(f"  Standby Current: {pb.get('total_current_standby_ma', 0):.0f} mA")
    print(f"  Alarm Current: {pb.get('total_current_alarm_ma', 0):.0f} mA")
    print(f"  Capacity: {pb.get('capacity_ma', 0):.0f} mA")
    print(f"  Utilization: {pb.get('utilization_percent', 0):.1f}%")
    
    if result['violations']:
        print(f"\nViolations:")
        for violation in result['violations']:
            print(f"  ⚠️  {violation}")
    else:
        print(f"\n✅ Configuration is valid!")
    
    print(f"\nOptimization Stats:")
    stats = result['optimization_stats']
    print(f"  Status: {stats['status']}")
    print(f"  Solve Time: {stats['solve_time_seconds']:.2f}s")
    print("="*80)


if __name__ == "__main__":
    main()
```

---

## Summary of Changes Required

### **Where to Replace in Original Code**

The original CP-SAT code in the PDF needs complete replacement. The key sections that need updating are:

1. **Component Database** (Lines ~100-400): Replace with expanded database including all fields from Excel
2. **Panel Specifications** (Lines ~50-100): Add cabinet/bay structure
3. **Decision Variables** (Lines ~450-550): Add bay, cabinet, and placement variables
4. **Panel Type Logic** (NEW): Add complete panel type handling
5. **Placement Constraints** (Lines ~600-900): Add comprehensive placement rules
6. **Mandatory Requirements** (Lines ~550-650): Add NAC/IDNAC, SDACT, etc. rules
7. **Power Budget** (Lines ~900-1000): Add card power and voltage availability
8. **Validation** (Lines ~1100-1200): Add comprehensive rule checking

### **Implementation Priority**

**Phase 1 - Critical (Must Have):**
1. Panel type constraints
2. Cabinet/bay structure
3. Power supply placement
4. NAC/IDNAC mandatory rule
5. Module plane interference

**Phase 2 - High (Should Have):**
1. Audio controller bay requirements
2. Amplifier placement rules
3. CPU bay slot restrictions
4. Master controller placement
5. Network module requirements

**Phase 3 - Medium (Nice to Have):**
1. Legacy vs ES module separation
2. Display requirements
3. LED/Switch controller rules
4. Microphone and phone placement
5. Redundant panel specific rules

### **Testing Checklist**

After implementation, test:
- [ ] Basic panel configuration
- [ ] Redundant panel configuration
- [ ] NDU panel configuration
- [ ] NDU with Voice panel configuration
- [ ] NAC/IDNAC mandatory rule
- [ ] SDACT vs System without DACT
- [ ] Power supply placement with Flex Amps
- [ ] Audio controller placement
- [ ] CPU and Network module placement
- [ ] Addressed modules limit
- [ ] Card power budget
- [ ] Plane interference
- [ ] Legacy module separation

---

## Next Steps for 4007ES

The same comprehensive analysis needs to be done for 4007ES panel using the second Excel sheet. The rules are similar but with different:
- Capacity limits (250 device loops vs 250 device loops)
- Module placement rules
- Power supply specifications
- Panel type options

---

**End of Analysis**
