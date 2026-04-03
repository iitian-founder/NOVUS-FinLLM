from .forensic_investigator import ForensicInvestigatorV3
from .narrative_decoder import NarrativeDecoderV3
from .moat_architect import MoatArchitectV3
from .capital_allocator import CapitalAllocatorV3
from .management_quality import ManagementQualityV3
from .forensic_quant import ForensicQuantV3
from .pm_synthesis import PMSynthesisV3

ALL_AGENTS = {
    "forensic_investigator": ForensicInvestigatorV3,
    "narrative_decoder":     NarrativeDecoderV3,
    "moat_architect":        MoatArchitectV3,
    "capital_allocator":     CapitalAllocatorV3,
    "management_quality":    ManagementQualityV3,
    "forensic_quant":        ForensicQuantV3,
    "pm_synthesis":          PMSynthesisV3,
}
