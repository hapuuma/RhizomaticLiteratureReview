"""
Stage 5: Rupture Protocol
Evaluates whether the dominant frameworks have overwhelmed analysis
and constructs the outside-view re-entry point if so.
"""
from models import ResonanceOutput, RuptureOutput


OUTSIDE_VIEWS = [
    "degrowth economics and the politics of sufficiency",
    "post-colonial Science and Technology Studies (STS)",
    "indigenous ontologies and territorial cosmologies",
    "feminist political ecology and care economies",
    "queer temporalities and non-linear imaginaries",
    "anarchist infrastructure theory and mutual aid networks",
]


def run_rupture_protocol(resonance: ResonanceOutput) -> RuptureOutput:
    """
    Synchronously evaluates the resonance output.
    If rupture_trigger is True, selects outside-view entry points
    based on the ruptured frameworks.
    No LLM call needed — this is deterministic routing logic.
    """
    if not resonance.rupture_trigger:
        return RuptureOutput(
            triggered=False,
            dominant_frameworks_ruptured=[],
            outside_view_entry_points=[],
            rupture_narrative=(
                "No asignifying rupture is being triggered at this moment. "
                "The dominant frameworks are not yet fully enclosing the analysis space; "
                "marginal connections are remaining accessible."
            ),
        )

    # Select outside views — rotate through the list to avoid repetition
    selected = OUTSIDE_VIEWS[:3]

    narrative = (
        f"An asignifying rupture is being initiated. The following dominant frameworks "
        f"are being identified as capturing the analysis: "
        f"{', '.join(resonance.dominant_frameworks_ruptured or ['unspecified frameworks'])}. "
        f"The research trajectory is now re-entering from outside, through the lenses of: "
        f"{', '.join(selected)}. These vantage points are opening unexpected lines of flight "
        f"that the enclosed frameworks are not able to contain."
    )

    return RuptureOutput(
        triggered=True,
        dominant_frameworks_ruptured=resonance.rupture_rationale.split(". ")
        if resonance.rupture_rationale
        else [],
        outside_view_entry_points=selected,
        rupture_narrative=narrative,
    )
