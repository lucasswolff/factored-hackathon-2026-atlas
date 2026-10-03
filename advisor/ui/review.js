const reasonNames = {
  score_below_demo_threshold: "Score below the synthetic threshold",
  score_near_demo_threshold: "Score in the human-review band",
  student_enrollment_unverified: "Student enrollment unverified",
  student_status_unverified: "Student status unverified",
  current_credit_card_requires_review: "Current credit card requires review",
  missing_profile_data: "Required profile field missing",
  income_below_demo_threshold: "Estimated income below the synthetic threshold",
  synthetic_thresholds_met: "Numeric synthetic thresholds met"
};

function cell(row, value, tag = "td") {
  const element = document.createElement(tag);
  element.textContent = value == null || value === "" ? "—" : String(value);
  row.append(element);
}

function renderTable(id, headings, records, columns) {
  const holder = document.getElementById(id);
  holder.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("p");
    empty.textContent = "No records yet.";
    holder.append(empty);
    return;
  }
  const table = document.createElement("table");
  table.className = "review-table";
  const head = table.createTHead().insertRow();
  for (const heading of headings) cell(head, heading, "th");
  const body = table.createTBody();
  for (const record of records) {
    const row = body.insertRow();
    for (const column of columns) cell(row, column(record));
  }
  holder.append(table);
}

async function loadReview() {
  try {
    const response = await fetch("/api/review", {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Review queue unavailable");
    renderTable("applicationsList",
      ["Reference", "Fixture", "Country", "Card", "Precheck", "Reason summary", "Status"],
      data.applications,
      [r => r.application_id, r => r.customer_alias, r => r.country, r => r.card,
       r => r.precheck_status || "Not run",
       r => (r.precheck_reasons || []).map(reason => reasonNames[reason] || reason).join("; ") || "No precheck reasons recorded",
       r => r.status]);
    renderTable("handoffsList",
      ["Reference", "Fixture", "Country", "Language", "Card", "Reason", "Verified context", "Prior actions", "Open questions", "Status", "Mock assignee"],
      data.handoffs,
      [r => r.handoff_id, r => r.customer_alias, r => r.country,
       r => r.language === "pt" ? "Portuguese" : "Spanish", r => r.card,
       r => r.packet?.request || (r.reason === "CUSTOMER_REQUEST" ? "Customer asked for a person" : r.reason),
       r => r.packet ? `${r.packet.verified_facts.segment} segment; current card: ${r.packet.verified_facts.has_current_credit_card ? "yes" : "no"}; ${r.packet.verified_facts.source}; offer ${r.packet.evidence.offer_version}; facts ${r.packet.evidence.fact_version}` : "Legacy record: context unavailable",
       r => r.packet ? [
         ...r.packet.actions_taken.prechecks.map(p => `${p.card}: ${p.status} (${p.reasons.join(", ") || "no reasons"}); policy ${p.policy_version}; consent ${p.consent_at}`),
         r.packet.actions_taken.application ? `Application ${r.packet.actions_taken.application.reference}: ${r.packet.actions_taken.application.status}` : "No application recorded"
       ].join("; ") : "Unavailable",
       r => r.packet ? [r.packet.unresolved_question, ...r.packet.open_questions].filter(Boolean).join("; ") : "Unavailable",
       r => r.status,
       r => r.packet?.assignment ? `${r.packet.assignment.agent_id} (mock roster assignment)` : "Unassigned"]);
  } catch (error) {
    const alert = document.getElementById("reviewError");
    alert.hidden = false;
    alert.textContent = error.message;
  }
}

loadReview();
