"""
Q&A Processor and Multi-Panel BOQ Handler for CP-SAT Engine
============================================================

This module processes project Q&A Excel files and BOQ data to generate
proper configuration constraints for the CP-SAT optimizer.

Features:
1. Read Q&A Excel and convert to configuration constraints
2. Handle multi-panel projects by dividing device quantities
3. Create separate configurations for remote annunciators
4. Generate JSON/Python dict format for CP-SAT input

Author: Fire Alarm System Configurator
Date: 2024
"""

import pandas as pd
import openpyxl
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import math


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class ProtocolType(Enum):
    """Device protocol type"""
    IDNET2 = "idnet2"
    MX = "mx"
    

class PanelSeries(Enum):
    """Panel series type"""
    PANEL_4100ES = "4100ES"
    PANEL_4007ES = "4007ES"
    PANEL_4010ES = "4010ES"


class AudioType(Enum):
    """Audio system type"""
    NO_AUDIO = "no_audio"
    BASIC_AUDIO = "basic_audio"
    VOICE_EVACUATION = "voice_evacuation"


@dataclass
class ProjectAnswers:
    """
    Structured answers from Q&A Excel file.
    Maps directly to CP-SAT configuration constraints.
    """
    # Protocol Selection (Q2-Q7)
    has_short_circuit_isolator: bool = False
    has_soft_addressable: bool = False
    has_loop_powered_sounder: bool = False
    detection_notification_same_loop: bool = False
    no_separate_notification_wiring: bool = False
    
    # Protocol determined from above
    protocol: ProtocolType = ProtocolType.IDNET2  # Default
    
    # Audio System (Q8-Q10, Q18-Q22, Q30)
    has_voice_evacuation: bool = False
    has_speakers: bool = False
    has_horns: bool = False
    audio_type: AudioType = AudioType.NO_AUDIO
    
    # Speaker Configuration
    speaker_wattage: float = 0.0
    dual_amplifier_per_zone: bool = False
    constant_supervision_speaker: bool = False
    backup_amplifier_one_to_one: bool = False
    backup_amplifier_one_for_all: bool = False
    speakers_with_visual: bool = False
    
    # NAC Configuration (Q11-Q12, Q15)
    use_addressable_nac: bool = False
    nac_class_a_wiring: bool = False
    
    # Display Type (Q13)
    display_type: str = "2x40_lcd"  # "2x40_lcd", "touch_screen"
    
    # Fire Fighter Phone (Q14, Q17)
    has_fire_phone: bool = False
    fire_phone_jack_count: int = 0
    
    # Speaker Circuit Class (Q16)
    speaker_class_a_wiring: bool = False
    
    # Integration (Q23-Q24, Q27, Q29)
    has_panel_printer: bool = False
    has_graphics_command_center: bool = False
    network_type: str = "none"  # "none", "ethernet", "smfo", "mmfo"
    graphics_software_type: str = "none"  # "none", "view_only", "full_control"
    
    # Annunciator (Q25, Q35)
    annunciator_type: str = "none"  # "none", "led", "lcd", "mimic"
    remote_annunciator_with_audio_control: bool = False
    
    # Smoke Management (Q26)
    has_smoke_management: bool = False
    smoke_management_relay_count: int = 0
    
    # Door Holders (Q28)
    door_holder_voltage: str = "24vdc"  # "24vdc", "220vac"
    
    # Monitor/Control Modules (Q31-Q34)
    monitor_modules_with_leds: bool = False
    fire_damper_feedback: bool = False
    fire_damper_led_indication: bool = False
    audio_control_led_switches: bool = False


@dataclass
class DeviceBOQ:
    """
    Bill of Quantities for field devices.
    Can be specified as generic types or Simplex part numbers.
    """
    # Detection Devices
    smoke_detector: int = 0
    heat_detector: int = 0
    duct_detector: int = 0
    beam_detector: int = 0
    manual_station: int = 0
    
    # Notification Devices (Conventional)
    horn_strobe: int = 0
    strobe_only: int = 0
    horn_only: int = 0
    
    # Notification Devices (Addressable)
    addressable_horn_strobe: int = 0
    addressable_strobe: int = 0
    
    # Audio Devices
    speaker: int = 0
    speaker_strobe: int = 0
    
    # Monitor/Control
    monitor_module: int = 0
    control_relay: int = 0
    
    # Special Devices
    fire_phone_jack: int = 0
    remote_annunciator: int = 0
    
    # Simplex Part Numbers (Optional)
    simplex_devices: Dict[str, int] = None  # {"4098-9756": 100, ...}


@dataclass
class PanelConfiguration:
    """Configuration for a single panel"""
    panel_id: str
    panel_series: PanelSeries
    boq: DeviceBOQ
    constraints: Dict
    is_main_panel: bool = True
    is_remote_annunciator: bool = False


# ============================================================================
# Q&A EXCEL PROCESSOR
# ============================================================================

class QandAProcessor:
    """
    Processes Q&A Excel file and converts answers to configuration constraints.
    """
    
    def __init__(self, excel_path: str):
        """
        Initialize processor with Q&A Excel file.
        
        Args:
            excel_path: Path to Q&A Excel file
        """
        self.excel_path = excel_path
        self.df = None
        self.answers = ProjectAnswers()
        
        # Load Excel
        self._load_excel()
    
    
    def _load_excel(self):
        """Load Q&A Excel file"""
        try:
            # Read Excel file
            self.df = pd.read_excel(self.excel_path, sheet_name='Sheet1')
            print(f"✓ Loaded Q&A Excel: {self.excel_path}")
            print(f"  Found {len(self.df)} questions")
        except Exception as e:
            raise ValueError(f"Failed to load Q&A Excel: {e}")
    
    
    def process_answers(self, answers_dict: Dict[int, str]) -> ProjectAnswers:
        """
        Process answers and populate ProjectAnswers structure.
        
        Args:
            answers_dict: Dictionary of {question_number: answer}
                         Example: {2: "yes", 3: "no", 8: "yes", ...}
        
        Returns:
            ProjectAnswers object with all fields populated
        """
        print("\n" + "="*80)
        print("PROCESSING Q&A ANSWERS")
        print("="*80)
        
        # Convert answers to lowercase for consistency
        answers = {k: str(v).lower().strip() for k, v in answers_dict.items()}
        
        # Q2-Q7: Protocol Selection
        self.answers.has_short_circuit_isolator = answers.get(2) == 'yes'
        self.answers.has_soft_addressable = answers.get(3) == 'yes'
        self.answers.has_loop_powered_sounder = answers.get(5) == 'yes'
        self.answers.detection_notification_same_loop = answers.get(6) == 'yes'
        self.answers.no_separate_notification_wiring = answers.get(7) == 'yes'
        
        # Determine protocol based on Q2-Q7
        if (self.answers.has_short_circuit_isolator or
            self.answers.has_soft_addressable or
            self.answers.has_loop_powered_sounder or
            self.answers.detection_notification_same_loop or
            self.answers.no_separate_notification_wiring):
            self.answers.protocol = ProtocolType.MX
            print("  → Protocol: MX (based on Q2-Q7)")
        else:
            self.answers.protocol = ProtocolType.IDNET2
            print("  → Protocol: IDNet2 (default)")
        
        # Q8-Q10: Audio System
        self.answers.has_voice_evacuation = answers.get(8) == 'yes'
        speakers_but_no_voice = answers.get(9) == 'yes'
        speakers_and_horns = answers.get(10) == 'yes'
        
        if self.answers.has_voice_evacuation:
            self.answers.audio_type = AudioType.VOICE_EVACUATION
            self.answers.has_speakers = True
            print("  → Audio: Voice Evacuation System (Q8)")
        elif speakers_and_horns:
            self.answers.audio_type = AudioType.VOICE_EVACUATION
            self.answers.has_speakers = True
            self.answers.has_horns = True
            print("  → Audio: Voice Evacuation with Horns (Q10)")
        else:
            self.answers.audio_type = AudioType.NO_AUDIO
            print("  → Audio: No Audio System")
        
        # Q11-Q12: Addressable NAC
        self.answers.use_addressable_nac = (
            answers.get(11) == 'yes' or answers.get(12) == 'yes'
        )
        if self.answers.use_addressable_nac:
            print("  → NAC Type: Addressable IDNAC (Q11/Q12)")
        
        # Q13: Display Type
        display_answer = answers.get(13, '').lower()
        if 'touch' in display_answer or 'tsd' in display_answer:
            self.answers.display_type = "touch_screen"
            print("  → Display: Touch Screen")
        else:
            self.answers.display_type = "2x40_lcd"
            print("  → Display: 2x40 LCD")
        
        # Q14: Fire Fighter Phone
        self.answers.has_fire_phone = answers.get(14) == 'yes'
        if self.answers.has_fire_phone:
            print("  → Fire Fighter Phone: Yes")
        
        # Q15: NAC Class A
        self.answers.nac_class_a_wiring = answers.get(15) == 'yes'
        
        # Q16: Speaker Class A
        self.answers.speaker_class_a_wiring = answers.get(16) == 'yes'
        
        # Q18: Dual Amplifier per Zone
        self.answers.dual_amplifier_per_zone = answers.get(18) == 'yes'
        
        # Q19: Constant Supervision
        self.answers.constant_supervision_speaker = answers.get(19) == 'yes'
        
        # Q20: Speaker Wattage (extract number)
        wattage_str = str(answers.get(20, '0'))
        try:
            self.answers.speaker_wattage = float(''.join(c for c in wattage_str if c.isdigit() or c == '.'))
        except:
            self.answers.speaker_wattage = 0.0
        
        if self.answers.speaker_wattage > 0:
            print(f"  → Speaker Wattage: {self.answers.speaker_wattage}W")
        
        # Q21-Q22: Backup Amplifiers
        self.answers.backup_amplifier_one_to_one = answers.get(21) == 'yes'
        self.answers.backup_amplifier_one_for_all = answers.get(22) == 'yes'
        
        # Q23: Panel Printer
        self.answers.has_panel_printer = answers.get(23) == 'yes'
        
        # Q24: Graphics Command Center
        self.answers.has_graphics_command_center = answers.get(24) == 'yes'
        
        # Q25: Annunciator Type
        annunciator_answer = answers.get(25, '').lower()
        if 'lcd' in annunciator_answer or 'rui' in annunciator_answer:
            self.answers.annunciator_type = "lcd"
        elif 'led' in annunciator_answer:
            self.answers.annunciator_type = "led"
        elif 'mimic' in annunciator_answer:
            self.answers.annunciator_type = "mimic"
        
        # Q26: Smoke Management
        self.answers.has_smoke_management = answers.get(26) == 'yes'
        relay_str = str(answers.get(26, '0'))
        try:
            self.answers.smoke_management_relay_count = int(''.join(c for c in relay_str if c.isdigit()))
        except:
            self.answers.smoke_management_relay_count = 0
        
        # Q27: Network Type
        network_answer = answers.get(27, '').lower()
        if 'smfo' in network_answer or 'single' in network_answer:
            self.answers.network_type = "smfo"
        elif 'mmfo' in network_answer or 'multi' in network_answer:
            self.answers.network_type = "mmfo"
        elif 'ethernet' in network_answer or 'wired' in network_answer:
            self.answers.network_type = "ethernet"
        
        # Q28: Door Holder Voltage
        door_answer = answers.get(28, '').lower()
        if '220' in door_answer or 'ac' in door_answer:
            self.answers.door_holder_voltage = "220vac"
        
        # Q29: Graphics Software
        graphics_answer = answers.get(29, '').lower()
        if 'full' in graphics_answer or 'control' in graphics_answer or 'disable' in graphics_answer:
            self.answers.graphics_software_type = "full_control"
        elif 'view' in graphics_answer or 'economic' in graphics_answer:
            self.answers.graphics_software_type = "view_only"
        
        # Q30: Speakers with Visual
        self.answers.speakers_with_visual = answers.get(30) == 'yes'
        
        # Q31: Monitor Modules with LEDs
        self.answers.monitor_modules_with_leds = answers.get(31) == 'yes'
        
        # Q32: Fire Damper Feedback
        self.answers.fire_damper_feedback = answers.get(32) == 'yes'
        
        # Q33: Fire Damper LED Indication
        self.answers.fire_damper_led_indication = answers.get(33) == 'yes'
        
        # Q34: Audio Control LED/Switches
        self.answers.audio_control_led_switches = answers.get(34) == 'yes'
        
        # Q35: Remote Annunciator with Audio Control
        self.answers.remote_annunciator_with_audio_control = answers.get(35) == 'yes'
        
        print("="*80)
        print("✓ Q&A Processing Complete")
        print("="*80 + "\n")
        
        return self.answers
    
    
    def to_cpsat_constraints(self) -> Dict:
        """
        Convert ProjectAnswers to CP-SAT configuration constraints format.
        
        Returns:
            Dictionary suitable for CP-SAT optimizer
        """
        constraints = {
            # Protocol
            "protocol": self.answers.protocol.value,
            "prefer_idnet2": self.answers.protocol == ProtocolType.IDNET2,
            "prefer_mx": self.answers.protocol == ProtocolType.MX,
            
            # Audio System
            "voice_evacuation": self.answers.audio_type == AudioType.VOICE_EVACUATION,
            "audio_type": "analog" if self.answers.audio_type != AudioType.NO_AUDIO else None,
            
            # Speaker Configuration
            "speaker_wattage_total": self.answers.speaker_wattage,
            "dual_amplifier_per_zone": self.answers.dual_amplifier_per_zone,
            "constant_supervision_speaker": self.answers.constant_supervision_speaker,
            "backup_amplifier_one_to_one": self.answers.backup_amplifier_one_to_one,
            "backup_amplifier_one_for_all": self.answers.backup_amplifier_one_for_all,
            "speakers_with_visual": self.answers.speakers_with_visual,
            
            # NAC Configuration
            "prefer_addressable_nac": self.answers.use_addressable_nac,
            "nac_class_a_wiring": self.answers.nac_class_a_wiring,
            "speaker_class_a_wiring": self.answers.speaker_class_a_wiring,
            
            # Display
            "display_type": self.answers.display_type,
            
            # Fire Phone
            "fire_phone_required": self.answers.has_fire_phone,
            "fire_phone_jack_count": self.answers.fire_phone_jack_count,
            
            # Integration
            "printer_required": self.answers.has_panel_printer,
            "network_connection": self.answers.has_graphics_command_center or self.answers.network_type != "none",
            "network_type": self.answers.network_type,
            "graphics_command_center": self.answers.has_graphics_command_center,
            "graphics_software_type": self.answers.graphics_software_type,
            
            # Annunciator
            "annunciator_type": self.answers.annunciator_type,
            "remote_annunciator_with_audio": self.answers.remote_annunciator_with_audio_control,
            
            # Smoke Management
            "smoke_management": self.answers.has_smoke_management,
            "smoke_management_relay_count": self.answers.smoke_management_relay_count,
            
            # Door Holders
            "door_holder_voltage": self.answers.door_holder_voltage,
            
            # LEDs and Switches
            "monitor_modules_with_leds": self.answers.monitor_modules_with_leds,
            "fire_damper_feedback": self.answers.fire_damper_feedback,
            "fire_damper_led_indication": self.answers.fire_damper_led_indication,
            "audio_control_led_switches": self.answers.audio_control_led_switches,
        }
        
        # Remove None values
        constraints = {k: v for k, v in constraints.items() if v is not None}
        
        return constraints
    
    
    def export_to_json(self, output_path: str):
        """Export constraints to JSON file"""
        constraints = self.to_cpsat_constraints()
        with open(output_path, 'w') as f:
            json.dump(constraints, f, indent=2)
        print(f"✓ Exported constraints to: {output_path}")


# ============================================================================
# MULTI-PANEL BOQ HANDLER
# ============================================================================

class MultiPanelBOQHandler:
    """
    Handles multi-panel projects by dividing device quantities
    and creating separate configurations for each panel.
    """
    
    def __init__(self, total_boq: DeviceBOQ, num_panels: int):
        """
        Initialize handler with total BOQ and number of panels.
        
        Args:
            total_boq: Total device quantities for entire project
            num_panels: Number of panels in the project
        """
        self.total_boq = total_boq
        self.num_panels = num_panels
        self.panel_boqs: List[DeviceBOQ] = []
        
        print(f"\n{'='*80}")
        print(f"MULTI-PANEL PROJECT: {num_panels} Panels")
        print('='*80)
    
    
    def divide_boq(self, strategy: str = "equal") -> List[DeviceBOQ]:
        """
        Divide total BOQ among multiple panels.
        
        Args:
            strategy: Division strategy
                     "equal" - Divide equally (default)
                     "balanced" - Balance by loop capacity
                     "custom" - Custom distribution
        
        Returns:
            List of DeviceBOQ objects, one per panel
        """
        if strategy == "equal":
            return self._divide_equal()
        elif strategy == "balanced":
            return self._divide_balanced()
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    
    def _divide_equal(self) -> List[DeviceBOQ]:
        """
        Divide BOQ equally among all panels.
        Uses ceiling division to ensure all devices are accommodated.
        """
        print(f"\nDividing BOQ equally among {self.num_panels} panels...")
        
        self.panel_boqs = []
        
        for panel_idx in range(self.num_panels):
            # Calculate devices per panel (ceiling division)
            panel_boq = DeviceBOQ(
                smoke_detector=math.ceil(self.total_boq.smoke_detector / self.num_panels),
                heat_detector=math.ceil(self.total_boq.heat_detector / self.num_panels),
                duct_detector=math.ceil(self.total_boq.duct_detector / self.num_panels),
                beam_detector=math.ceil(self.total_boq.beam_detector / self.num_panels),
                manual_station=math.ceil(self.total_boq.manual_station / self.num_panels),
                horn_strobe=math.ceil(self.total_boq.horn_strobe / self.num_panels),
                strobe_only=math.ceil(self.total_boq.strobe_only / self.num_panels),
                horn_only=math.ceil(self.total_boq.horn_only / self.num_panels),
                addressable_horn_strobe=math.ceil(self.total_boq.addressable_horn_strobe / self.num_panels),
                addressable_strobe=math.ceil(self.total_boq.addressable_strobe / self.num_panels),
                speaker=math.ceil(self.total_boq.speaker / self.num_panels),
                speaker_strobe=math.ceil(self.total_boq.speaker_strobe / self.num_panels),
                monitor_module=math.ceil(self.total_boq.monitor_module / self.num_panels),
                control_relay=math.ceil(self.total_boq.control_relay / self.num_panels),
                fire_phone_jack=math.ceil(self.total_boq.fire_phone_jack / self.num_panels),
                remote_annunciator=0,  # Handled separately
            )
            
            self.panel_boqs.append(panel_boq)
            
            print(f"\n  Panel {panel_idx + 1}:")
            print(f"    Smoke Detectors: {panel_boq.smoke_detector}")
            print(f"    Heat Detectors: {panel_boq.heat_detector}")
            print(f"    Manual Stations: {panel_boq.manual_station}")
            print(f"    Horn/Strobes: {panel_boq.horn_strobe}")
            print(f"    Speakers: {panel_boq.speaker}")
        
        print(f"\n✓ BOQ division complete")
        return self.panel_boqs
    
    
    def _divide_balanced(self) -> List[DeviceBOQ]:
        """
        Divide BOQ balancing by loop capacity.
        Ensures no panel is overloaded.
        """
        # Calculate total devices that go on loops
        total_loop_devices = (
            self.total_boq.smoke_detector +
            self.total_boq.heat_detector +
            self.total_boq.duct_detector +
            self.total_boq.beam_detector +
            self.total_boq.manual_station +
            self.total_boq.monitor_module
        )
        
        # IDNet2 capacity: 250 devices per loop
        max_devices_per_panel = 250 * 10  # Assuming 10 loops max per panel
        
        if total_loop_devices / self.num_panels > max_devices_per_panel:
            print(f"⚠️  Warning: Device count may exceed panel capacity")
            print(f"   Total devices: {total_loop_devices}")
            print(f"   Devices per panel: {total_loop_devices / self.num_panels:.0f}")
            print(f"   Max per panel: {max_devices_per_panel}")
        
        # For now, use equal division
        # TODO: Implement smart balancing algorithm
        return self._divide_equal()


# ============================================================================
# REMOTE ANNUNCIATOR HANDLER
# ============================================================================

class RemoteAnnunciatorHandler:
    """
    Creates separate panel configuration for remote annunciators
    with audio control capabilities.
    """
    
    @staticmethod
    def create_annunciator_config(
        main_panel_constraints: Dict,
        has_audio_control: bool = False,
        has_microphone: bool = False,
        has_led_switches: bool = False,
    ) -> PanelConfiguration:
        """
        Create a remote annunciator panel configuration.
        
        Args:
            main_panel_constraints: Constraints from main panel
            has_audio_control: Include audio control capability
            has_microphone: Include microphone
            has_led_switches: Include LED/switch modules
        
        Returns:
            PanelConfiguration for remote annunciator
        """
        print("\n" + "="*80)
        print("CREATING REMOTE ANNUNCIATOR CONFIGURATION")
        print("="*80)
        
        # Remote annunciator has minimal device BOQ
        annunciator_boq = DeviceBOQ(
            # No field devices, just interface
            smoke_detector=0,
            heat_detector=0,
            remote_annunciator=1,  # The annunciator itself
        )
        
        # Copy relevant constraints from main panel
        annunciator_constraints = {
            "panel_type": "remote_annunciator",
            "protocol": main_panel_constraints.get("protocol", "idnet2"),
            "display_type": "touch_screen" if main_panel_constraints.get("display_type") == "touch_screen" else "2x40_lcd",
            "network_connection": True,  # Always networked to main panel
        }
        
        # Add audio control if requested
        if has_audio_control:
            annunciator_constraints.update({
                "has_audio_control": True,
                "audio_microphone": has_microphone,
                "audio_led_switches": has_led_switches,
                "panel_type": "remote_annunciator_with_incident_commander",
            })
            print("  → Type: Remote Annunciator with Audio Control")
        else:
            print("  → Type: Standard Remote Annunciator")
        
        # Create configuration
        config = PanelConfiguration(
            panel_id="ANNUNCIATOR-1",
            panel_series=PanelSeries.PANEL_4100ES,
            boq=annunciator_boq,
            constraints=annunciator_constraints,
            is_main_panel=False,
            is_remote_annunciator=True,
        )
        
        print("✓ Remote annunciator configuration created")
        print("="*80 + "\n")
        
        return config


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class ProjectConfigurator:
    """
    Main orchestrator that combines Q&A processing, BOQ handling,
    and generates complete project configuration for CP-SAT.
    """
    
    def __init__(self):
        self.qa_processor: Optional[QandAProcessor] = None
        self.project_answers: Optional[ProjectAnswers] = None
        self.panel_configurations: List[PanelConfiguration] = []
    
    
    def process_project(
        self,
        qa_excel_path: str,
        qa_answers: Dict[int, str],
        total_boq: DeviceBOQ,
        num_panels: int = 1,
    ) -> List[PanelConfiguration]:
        """
        Complete project processing workflow.
        
        Args:
            qa_excel_path: Path to Q&A Excel file
            qa_answers: Dictionary of answers to questions
            total_boq: Total device BOQ for project
            num_panels: Number of main panels
        
        Returns:
            List of PanelConfiguration objects ready for CP-SAT
        """
        print("\n" + "="*80)
        print("PROJECT CONFIGURATION WORKFLOW")
        print("="*80 + "\n")
        
        # Step 1: Process Q&A
        print("STEP 1: Processing Q&A Excel...")
        self.qa_processor = QandAProcessor(qa_excel_path)
        self.project_answers = self.qa_processor.process_answers(qa_answers)
        base_constraints = self.qa_processor.to_cpsat_constraints()
        
        # Step 2: Handle Fire Phone Jack Count
        if total_boq.fire_phone_jack > 0:
            # Calculate fire phone circuits (1 circuit per 10 jacks)
            fire_phone_circuits = math.ceil(total_boq.fire_phone_jack / 10)
            base_constraints["fire_phone_jack_count"] = total_boq.fire_phone_jack
            base_constraints["fire_phone_circuits"] = fire_phone_circuits
            print(f"\nFire Phone: {total_boq.fire_phone_jack} jacks → {fire_phone_circuits} circuits")
        
        # Step 3: Divide BOQ if multiple panels
        print(f"\nSTEP 2: Dividing BOQ for {num_panels} panel(s)...")
        if num_panels > 1:
            boq_handler = MultiPanelBOQHandler(total_boq, num_panels)
            panel_boqs = boq_handler.divide_boq(strategy="equal")
        else:
            panel_boqs = [total_boq]
        
        # Step 4: Create main panel configurations
        print(f"\nSTEP 3: Creating {num_panels} main panel configuration(s)...")
        for idx, panel_boq in enumerate(panel_boqs):
            config = PanelConfiguration(
                panel_id=f"PANEL-{idx + 1}",
                panel_series=PanelSeries.PANEL_4100ES,  # Default, can be changed
                boq=panel_boq,
                constraints=base_constraints.copy(),
                is_main_panel=True,
                is_remote_annunciator=False,
            )
            self.panel_configurations.append(config)
            print(f"  ✓ Created configuration for PANEL-{idx + 1}")
        
        # Step 5: Create remote annunciator if needed
        if self.project_answers.remote_annunciator_with_audio_control:
            print("\nSTEP 4: Creating remote annunciator configuration...")
            annunciator_config = RemoteAnnunciatorHandler.create_annunciator_config(
                main_panel_constraints=base_constraints,
                has_audio_control=True,
                has_microphone=self.project_answers.audio_control_led_switches,
                has_led_switches=self.project_answers.audio_control_led_switches,
            )
            self.panel_configurations.append(annunciator_config)
        
        # Add remote annunciators from BOQ
        if total_boq.remote_annunciator > 0 and not self.project_answers.remote_annunciator_with_audio_control:
            print(f"\nSTEP 5: Creating {total_boq.remote_annunciator} standard remote annunciator(s)...")
            for idx in range(total_boq.remote_annunciator):
                annunciator_config = RemoteAnnunciatorHandler.create_annunciator_config(
                    main_panel_constraints=base_constraints,
                    has_audio_control=False,
                    has_microphone=False,
                    has_led_switches=False,
                )
                annunciator_config.panel_id = f"ANNUNCIATOR-{idx + 1}"
                self.panel_configurations.append(annunciator_config)
        
        print("\n" + "="*80)
        print("✓ PROJECT CONFIGURATION COMPLETE")
        print(f"  Total configurations: {len(self.panel_configurations)}")
        print(f"  Main panels: {sum(1 for c in self.panel_configurations if c.is_main_panel)}")
        print(f"  Remote annunciators: {sum(1 for c in self.panel_configurations if c.is_remote_annunciator)}")
        print("="*80 + "\n")
        
        return self.panel_configurations
    
    
    def export_to_json(self, output_path: str):
        """Export all configurations to JSON file"""
        configs_dict = [
            {
                "panel_id": config.panel_id,
                "panel_series": config.panel_series.value,
                "is_main_panel": config.is_main_panel,
                "is_remote_annunciator": config.is_remote_annunciator,
                "boq": asdict(config.boq),
                "constraints": config.constraints,
            }
            for config in self.panel_configurations
        ]
        
        with open(output_path, 'w') as f:
            json.dump(configs_dict, f, indent=2)
        
        print(f"✓ Exported {len(self.panel_configurations)} configuration(s) to: {output_path}")
    
    
    def get_cpsat_inputs(self) -> List[Tuple[Dict, Dict]]:
        """
        Get BOQ and constraints for each panel in format ready for CP-SAT.
        
        Returns:
            List of (boq_dict, constraints_dict) tuples
        """
        cpsat_inputs = []
        
        for config in self.panel_configurations:
            # Convert DeviceBOQ to dictionary
            boq_dict = {
                "smoke_detector": config.boq.smoke_detector,
                "heat_detector": config.boq.heat_detector,
                "duct_detector": config.boq.duct_detector,
                "beam_detector": config.boq.beam_detector,
                "manual_station": config.boq.manual_station,
                "horn_strobe": config.boq.horn_strobe,
                "strobe_only": config.boq.strobe_only,
                "horn_only": config.boq.horn_only,
                "addressable_horn_strobe": config.boq.addressable_horn_strobe,
                "speaker": config.boq.speaker,
                "speaker_strobe": config.boq.speaker_strobe,
                "monitor_module": config.boq.monitor_module,
                "control_relay": config.boq.control_relay,
                "fire_phone_jack": config.boq.fire_phone_jack,
            }
            
            # Remove zero quantities
            boq_dict = {k: v for k, v in boq_dict.items() if v > 0}
            
            cpsat_inputs.append((boq_dict, config.constraints))
        
        return cpsat_inputs


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def main():
    """Example usage of the complete workflow"""
    
    # Step 1: Define Q&A answers
    qa_answers = {
        2: "no",   # Short-circuit isolator → IDNet2
        3: "no",   # Soft-addressable → IDNet2
        8: "yes",  # Voice evacuation
        11: "yes", # Addressable NAC
        13: "2x40", # Display type
        14: "yes", # Fire phone
        23: "yes", # Panel printer
        24: "yes", # Graphics command center
        27: "ethernet", # Network type
        35: "yes", # Remote annunciator with audio control
    }
    
    # Step 2: Define total project BOQ
    total_boq = DeviceBOQ(
        smoke_detector=500,
        heat_detector=100,
        manual_station=30,
        horn_strobe=200,
        speaker=150,
        monitor_module=50,
        control_relay=25,
        fire_phone_jack=15,
        remote_annunciator=2,
    )
    
    # Step 3: Process project (3 panels)
    configurator = ProjectConfigurator()
    configurations = configurator.process_project(
        qa_excel_path="/mnt/user-data/uploads/QandA_for_Panel.xlsx",
        qa_answers=qa_answers,
        total_boq=total_boq,
        num_panels=3,
    )
    
    # Step 4: Export to JSON
    configurator.export_to_json("/home/claude/project_configurations.json")
    
    # Step 5: Get CP-SAT inputs
    cpsat_inputs = configurator.get_cpsat_inputs()
    
    print("\n" + "="*80)
    print("CP-SAT READY INPUTS")
    print("="*80)
    for idx, (boq, constraints) in enumerate(cpsat_inputs, 1):
        print(f"\nPanel {idx}:")
        print(f"  BOQ: {boq}")
        print(f"  Constraints: {constraints}")
    
    return configurations


if __name__ == "__main__":
    main()
