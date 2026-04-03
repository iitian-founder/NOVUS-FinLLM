const fs = require('fs');

const data = {
    result: {
        final_report: "## Pm Synthesis...\n\n```json\n{\"executive_summary\": \"...\", \"flags\": []}\n```",
        agent_outputs: {
            narrative_decoder: "Narrative details...",
            forensic_quant: "**Data Gaps:**\n- No P&L data available"
        },
        triage_result: { passed: true, kill_reasons: [], warnings: [] },
        forensic_scorecard: null,
        status: "completed"
    }
};

let scorecard = data.result.forensic_scorecard;
if (!scorecard) {
    console.log("Scorecard is null, returning early in renderForensicPanel!");
} else {
    try {
        const eq = scorecard.earnings_quality?.quality_grade || '--';
        if (scorecard.flags?.length) {
            scorecard.flags.forEach(f => console.log(f));
        }
    } catch(e) { console.error("Crash in renderForensicPanel:", e); }
}

const agentOutputs = data.result.agent_outputs;
const narrativeStr = agentOutputs['narrative_decoder'] || '';
let score = 50;
if (narrativeStr.toLowerCase().includes('high evasion')) score = 85;
for (const [name, output] of Object.entries(agentOutputs)) {
    console.log("Rendering agent:", name);
}

console.log("No issues simulating JS logic!");
