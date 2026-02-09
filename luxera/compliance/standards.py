"""
Luxera Compliance Module

Checks lighting designs against international standards:
- EN 12464-1: Light and lighting - Lighting of work places (Indoor)
- EN 12464-2: Light and lighting - Lighting of work places (Outdoor)  
- CIBSE LG7: Lighting for offices
- IESNA RP-1: Office Lighting

This module provides:
- Standard requirement lookups
- Compliance checking against calculated values
- Reporting of pass/fail status with recommendations

Key metrics checked:
- Maintained illuminance (Em)
- Uniformity ratio (Uo)
- Unified Glare Rating (UGR)
- Color Rendering Index (CRI)
- Correlated Color Temperature (CCT)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum, auto


# =============================================================================
# Room/Activity Types
# =============================================================================

class ActivityType(Enum):
    """Types of activities for lighting requirements."""
    # Offices
    OFFICE_GENERAL = auto()
    OFFICE_WRITING = auto()
    OFFICE_TECHNICAL = auto()
    OFFICE_CAD = auto()
    CONFERENCE_ROOM = auto()
    RECEPTION = auto()
    
    # Industrial
    WAREHOUSE_GENERAL = auto()
    WAREHOUSE_LOADING = auto()
    MANUFACTURING_ROUGH = auto()
    MANUFACTURING_MEDIUM = auto()
    MANUFACTURING_FINE = auto()
    MANUFACTURING_VERY_FINE = auto()
    
    # Retail
    RETAIL_GENERAL = auto()
    RETAIL_SUPERMARKET = auto()
    RETAIL_CHECKOUT = auto()
    
    # Education
    CLASSROOM = auto()
    LECTURE_HALL = auto()
    LABORATORY = auto()
    LIBRARY_READING = auto()
    LIBRARY_SHELVES = auto()
    
    # Healthcare
    HOSPITAL_CORRIDOR = auto()
    HOSPITAL_WARD = auto()
    HOSPITAL_EXAMINATION = auto()
    HOSPITAL_OPERATING = auto()
    
    # Circulation
    CORRIDOR = auto()
    STAIRWAY = auto()
    LIFT_LOBBY = auto()
    ENTRANCE_HALL = auto()
    
    # Amenity
    CANTEEN = auto()
    KITCHEN = auto()
    TOILET = auto()
    CHANGING_ROOM = auto()
    
    # Parking
    PARKING_GARAGE = auto()
    
    # Custom
    CUSTOM = auto()


# =============================================================================
# Lighting Requirements
# =============================================================================

@dataclass
class LightingRequirement:
    """
    Lighting requirements for a specific activity type.
    
    Based on EN 12464-1:2021 and related standards.
    """
    activity_type: ActivityType
    description: str
    
    # Illuminance requirements
    maintained_illuminance: float  # Em in lux
    illuminance_min: Optional[float] = None  # Minimum acceptable
    illuminance_max: Optional[float] = None  # Maximum (for energy)
    
    # Uniformity requirements
    uniformity_min: float = 0.6  # Uo (Emin/Eavg)
    uniformity_immediate: float = 0.4  # Immediate surrounding area
    
    # Glare requirements
    ugr_max: float = 19  # Unified Glare Rating limit
    
    # Color requirements
    cri_min: int = 80  # Minimum Color Rendering Index
    cct_min: Optional[int] = None  # Correlated Color Temperature min (K)
    cct_max: Optional[int] = None  # CCT max (K)
    
    # Additional notes
    notes: str = ""
    standard_reference: str = "EN 12464-1:2021"


# EN 12464-1:2021 Requirement Database
EN_12464_1_REQUIREMENTS: Dict[ActivityType, LightingRequirement] = {
    # Offices (Table 5.1)
    ActivityType.OFFICE_GENERAL: LightingRequirement(
        activity_type=ActivityType.OFFICE_GENERAL,
        description="Writing, typing, reading, data processing",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.OFFICE_WRITING: LightingRequirement(
        activity_type=ActivityType.OFFICE_WRITING,
        description="Writing, typing, reading",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.OFFICE_TECHNICAL: LightingRequirement(
        activity_type=ActivityType.OFFICE_TECHNICAL,
        description="Technical drawing",
        maintained_illuminance=750,
        uniformity_min=0.7,
        ugr_max=16,
        cri_min=80,
    ),
    ActivityType.OFFICE_CAD: LightingRequirement(
        activity_type=ActivityType.OFFICE_CAD,
        description="CAD workstations",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
        notes="Consider screen reflections",
    ),
    ActivityType.CONFERENCE_ROOM: LightingRequirement(
        activity_type=ActivityType.CONFERENCE_ROOM,
        description="Conference and meeting rooms",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
        notes="Dimmable lighting recommended",
    ),
    ActivityType.RECEPTION: LightingRequirement(
        activity_type=ActivityType.RECEPTION,
        description="Reception desk",
        maintained_illuminance=300,
        uniformity_min=0.6,
        ugr_max=22,
        cri_min=80,
    ),
    
    # Industrial (Table 5.2)
    ActivityType.WAREHOUSE_GENERAL: LightingRequirement(
        activity_type=ActivityType.WAREHOUSE_GENERAL,
        description="Warehouses, stock handling",
        maintained_illuminance=100,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=60,
    ),
    ActivityType.WAREHOUSE_LOADING: LightingRequirement(
        activity_type=ActivityType.WAREHOUSE_LOADING,
        description="Loading bays",
        maintained_illuminance=150,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=60,
    ),
    ActivityType.MANUFACTURING_ROUGH: LightingRequirement(
        activity_type=ActivityType.MANUFACTURING_ROUGH,
        description="Rough work, machining",
        maintained_illuminance=300,
        uniformity_min=0.6,
        ugr_max=25,
        cri_min=60,
    ),
    ActivityType.MANUFACTURING_MEDIUM: LightingRequirement(
        activity_type=ActivityType.MANUFACTURING_MEDIUM,
        description="Medium work, assembly",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=22,
        cri_min=80,
    ),
    ActivityType.MANUFACTURING_FINE: LightingRequirement(
        activity_type=ActivityType.MANUFACTURING_FINE,
        description="Fine work, inspection",
        maintained_illuminance=750,
        uniformity_min=0.7,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.MANUFACTURING_VERY_FINE: LightingRequirement(
        activity_type=ActivityType.MANUFACTURING_VERY_FINE,
        description="Very fine work, precision assembly",
        maintained_illuminance=1000,
        uniformity_min=0.7,
        ugr_max=16,
        cri_min=90,
    ),
    
    # Education (Table 5.6)
    ActivityType.CLASSROOM: LightingRequirement(
        activity_type=ActivityType.CLASSROOM,
        description="Classrooms, tutorial rooms",
        maintained_illuminance=300,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
        notes="Vertical illuminance on boards important",
    ),
    ActivityType.LECTURE_HALL: LightingRequirement(
        activity_type=ActivityType.LECTURE_HALL,
        description="Lecture halls",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.LABORATORY: LightingRequirement(
        activity_type=ActivityType.LABORATORY,
        description="Laboratories",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.LIBRARY_READING: LightingRequirement(
        activity_type=ActivityType.LIBRARY_READING,
        description="Library reading areas",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=80,
    ),
    ActivityType.LIBRARY_SHELVES: LightingRequirement(
        activity_type=ActivityType.LIBRARY_SHELVES,
        description="Library shelves",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=19,
        cri_min=80,
    ),
    
    # Healthcare (Table 5.7)
    ActivityType.HOSPITAL_CORRIDOR: LightingRequirement(
        activity_type=ActivityType.HOSPITAL_CORRIDOR,
        description="Hospital corridors during day",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=22,
        cri_min=80,
    ),
    ActivityType.HOSPITAL_WARD: LightingRequirement(
        activity_type=ActivityType.HOSPITAL_WARD,
        description="Hospital ward general",
        maintained_illuminance=100,
        uniformity_min=0.4,
        ugr_max=19,
        cri_min=80,
        notes="Bedhead reading light 300 lux",
    ),
    ActivityType.HOSPITAL_EXAMINATION: LightingRequirement(
        activity_type=ActivityType.HOSPITAL_EXAMINATION,
        description="Examination rooms",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=90,
    ),
    ActivityType.HOSPITAL_OPERATING: LightingRequirement(
        activity_type=ActivityType.HOSPITAL_OPERATING,
        description="Operating theatre (general)",
        maintained_illuminance=1000,
        uniformity_min=0.6,
        ugr_max=19,
        cri_min=90,
        notes="Task area requires 10000-100000 lux",
    ),
    
    # Circulation (Table 5.1)
    ActivityType.CORRIDOR: LightingRequirement(
        activity_type=ActivityType.CORRIDOR,
        description="Corridors",
        maintained_illuminance=100,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=40,
    ),
    ActivityType.STAIRWAY: LightingRequirement(
        activity_type=ActivityType.STAIRWAY,
        description="Stairs, escalators",
        maintained_illuminance=100,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=40,
    ),
    ActivityType.LIFT_LOBBY: LightingRequirement(
        activity_type=ActivityType.LIFT_LOBBY,
        description="Lift lobbies",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=22,
        cri_min=80,
    ),
    ActivityType.ENTRANCE_HALL: LightingRequirement(
        activity_type=ActivityType.ENTRANCE_HALL,
        description="Entrance halls, lobbies",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=22,
        cri_min=80,
    ),
    
    # Amenity
    ActivityType.CANTEEN: LightingRequirement(
        activity_type=ActivityType.CANTEEN,
        description="Canteens, break rooms",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=22,
        cri_min=80,
    ),
    ActivityType.KITCHEN: LightingRequirement(
        activity_type=ActivityType.KITCHEN,
        description="Kitchen",
        maintained_illuminance=500,
        uniformity_min=0.6,
        ugr_max=22,
        cri_min=80,
    ),
    ActivityType.TOILET: LightingRequirement(
        activity_type=ActivityType.TOILET,
        description="Toilets, washrooms",
        maintained_illuminance=200,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=80,
    ),
    
    # Parking
    ActivityType.PARKING_GARAGE: LightingRequirement(
        activity_type=ActivityType.PARKING_GARAGE,
        description="Parking garages (traffic lanes)",
        maintained_illuminance=75,
        uniformity_min=0.4,
        ugr_max=25,
        cri_min=40,
    ),
}


# =============================================================================
# Compliance Checking
# =============================================================================

class ComplianceStatus(Enum):
    """Status of a compliance check."""
    PASS = auto()
    FAIL = auto()
    WARNING = auto()
    NOT_APPLICABLE = auto()


@dataclass
class ComplianceCheck:
    """Result of a single compliance check."""
    parameter: str
    status: ComplianceStatus
    required_value: float
    actual_value: float
    unit: str
    message: str
    recommendation: Optional[str] = None


@dataclass
class ComplianceReport:
    """Complete compliance report for a room or area."""
    room_name: str
    activity_type: ActivityType
    requirement: LightingRequirement
    checks: List[ComplianceCheck] = field(default_factory=list)
    
    @property
    def is_compliant(self) -> bool:
        """Check if all requirements are met."""
        return all(c.status in (ComplianceStatus.PASS, ComplianceStatus.NOT_APPLICABLE) 
                  for c in self.checks)
    
    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == ComplianceStatus.PASS)
    
    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == ComplianceStatus.FAIL)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.status == ComplianceStatus.WARNING)
    
    def summary(self) -> str:
        """Generate summary text."""
        total = len(self.checks)
        status = "COMPLIANT" if self.is_compliant else "NON-COMPLIANT"
        return (f"{self.room_name}: {status}\n"
                f"  Activity: {self.requirement.description}\n"
                f"  Standard: {self.requirement.standard_reference}\n"
                f"  Results: {self.pass_count} pass, {self.fail_count} fail, "
                f"{self.warning_count} warning of {total} checks")


def check_compliance(
    room_name: str,
    activity_type: ActivityType,
    maintained_illuminance: float,
    uniformity: float,
    ugr: Optional[float] = None,
    cri: Optional[int] = None,
    cct: Optional[int] = None,
) -> ComplianceReport:
    """
    Check if calculated lighting values comply with standards.
    
    Args:
        room_name: Name of the room/area
        activity_type: Type of activity in the space
        maintained_illuminance: Average maintained illuminance (lux)
        uniformity: Uniformity ratio Uo (Emin/Eavg)
        ugr: Unified Glare Rating (optional)
        cri: Color Rendering Index (optional)
        cct: Correlated Color Temperature in K (optional)
    
    Returns:
        ComplianceReport with detailed results
    """
    if activity_type not in EN_12464_1_REQUIREMENTS:
        # Custom or unknown - use general office as default
        activity_type = ActivityType.OFFICE_GENERAL
    
    req = EN_12464_1_REQUIREMENTS[activity_type]
    report = ComplianceReport(
        room_name=room_name,
        activity_type=activity_type,
        requirement=req,
    )
    
    # Check maintained illuminance
    if maintained_illuminance >= req.maintained_illuminance:
        status = ComplianceStatus.PASS
        msg = f"Illuminance {maintained_illuminance:.0f} lux meets requirement"
        rec = None
    elif maintained_illuminance >= req.maintained_illuminance * 0.9:
        status = ComplianceStatus.WARNING
        msg = f"Illuminance {maintained_illuminance:.0f} lux is marginally below requirement"
        rec = "Consider adding luminaires or increasing lamp output"
    else:
        status = ComplianceStatus.FAIL
        msg = f"Illuminance {maintained_illuminance:.0f} lux below minimum {req.maintained_illuminance} lux"
        shortfall = req.maintained_illuminance - maintained_illuminance
        rec = f"Increase illuminance by {shortfall:.0f} lux"
    
    report.checks.append(ComplianceCheck(
        parameter="Maintained Illuminance (Em)",
        status=status,
        required_value=req.maintained_illuminance,
        actual_value=maintained_illuminance,
        unit="lux",
        message=msg,
        recommendation=rec,
    ))
    
    # Check uniformity
    if uniformity >= req.uniformity_min:
        status = ComplianceStatus.PASS
        msg = f"Uniformity {uniformity:.2f} meets requirement"
        rec = None
    elif uniformity >= req.uniformity_min * 0.9:
        status = ComplianceStatus.WARNING
        msg = f"Uniformity {uniformity:.2f} is marginally below requirement"
        rec = "Adjust luminaire spacing for better uniformity"
    else:
        status = ComplianceStatus.FAIL
        msg = f"Uniformity {uniformity:.2f} below minimum {req.uniformity_min}"
        rec = "Reduce luminaire spacing or add luminaires to dark areas"
    
    report.checks.append(ComplianceCheck(
        parameter="Uniformity Ratio (Uo)",
        status=status,
        required_value=req.uniformity_min,
        actual_value=uniformity,
        unit="",
        message=msg,
        recommendation=rec,
    ))
    
    # Check UGR if provided
    if ugr is not None:
        if ugr <= req.ugr_max:
            status = ComplianceStatus.PASS
            msg = f"UGR {ugr:.0f} meets requirement"
            rec = None
        else:
            status = ComplianceStatus.FAIL
            msg = f"UGR {ugr:.0f} exceeds maximum {req.ugr_max}"
            rec = "Use lower-glare luminaires or improve shielding"
        
        report.checks.append(ComplianceCheck(
            parameter="Unified Glare Rating (UGR)",
            status=status,
            required_value=req.ugr_max,
            actual_value=ugr,
            unit="",
            message=msg,
            recommendation=rec,
        ))
    
    # Check CRI if provided
    if cri is not None:
        if cri >= req.cri_min:
            status = ComplianceStatus.PASS
            msg = f"CRI {cri} meets requirement"
            rec = None
        else:
            status = ComplianceStatus.FAIL
            msg = f"CRI {cri} below minimum {req.cri_min}"
            rec = "Use lamps with higher CRI rating"
        
        report.checks.append(ComplianceCheck(
            parameter="Color Rendering Index (CRI)",
            status=status,
            required_value=float(req.cri_min),
            actual_value=float(cri),
            unit="Ra",
            message=msg,
            recommendation=rec,
        ))
    
    return report


def check_compliance_from_grid(
    room_name: str,
    activity_type: ActivityType,
    grid_values_lux: List[float],
    maintenance_factor: float = 1.0,
    ugr: Optional[float] = None,
    cri: Optional[int] = None,
    cct: Optional[int] = None,
) -> ComplianceReport:
    """
    Check compliance using grid illuminance values.

    Maintained illuminance is computed as mean(grid) * maintenance_factor.
    Uniformity is Emin/Eavg from the grid.
    """
    if not grid_values_lux:
        raise ValueError("Grid values are empty")

    avg = sum(grid_values_lux) / len(grid_values_lux)
    mn = min(grid_values_lux)

    maintained = avg * maintenance_factor
    uniformity = (mn / avg) if avg > 0 else 0.0

    return check_compliance(
        room_name=room_name,
        activity_type=activity_type,
        maintained_illuminance=maintained,
        uniformity=uniformity,
        ugr=ugr,
        cri=cri,
        cct=cct,
    )


def get_requirement(activity_type: ActivityType) -> LightingRequirement:
    """Get lighting requirement for an activity type."""
    if activity_type in EN_12464_1_REQUIREMENTS:
        return EN_12464_1_REQUIREMENTS[activity_type]
    return EN_12464_1_REQUIREMENTS[ActivityType.OFFICE_GENERAL]


def list_activity_types() -> List[Tuple[ActivityType, str]]:
    """Get list of all activity types with descriptions."""
    return [
        (at, req.description)
        for at, req in EN_12464_1_REQUIREMENTS.items()
    ]
