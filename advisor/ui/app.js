const $ = (id) => document.getElementById(id);
const cardInfo = {
  Campus: { audience: "For students", benefit: "Spending controls, reminders and education rewards. No annual fee.", icon: "◈" },
  Horizon: { audience: "Everyday essentials", benefit: "Everyday rewards, useful alerts and straightforward support. No annual fee.", icon: "↗" },
  Rewards: { audience: "More from every journey", benefit: "1 mile per USD-equivalent purchase, 2 proposed lounge visits and travel coverage.", icon: "✧" },
  Summit: { audience: "Premium travel", benefit: "2 miles per USD-equivalent purchase, 8 proposed lounge visits and broader coverage.", icon: "✳" }
};
const prompts = {
  es: ["¿Qué beneficios tiene esta tarjeta?", "¿Qué tarjeta me recomiendas?", "Quiero solicitar esta tarjeta"],
  pt: ["Quais são os benefícios deste cartão?", "Qual cartão você me recomenda?", "Quero solicitar este cartão"]
};
let state = null;
let busy = false;
let waitingSince = 0;
let timer = null;
let pendingEntry = null;
let pendingMessage = null;
let previewRequest = 0;

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function child(parent, tag, className, text) {
  const el = node(tag, className, text);
  parent.append(el);
  return el;
}
function row(box, label, value) {
  const line = child(box, "div", "evidence-row");
  child(line, "span", "", label);
  child(line, "span", "", value == null ? "—" : String(value));
}
function box(parent, title) {
  const el = child(parent, "div", "evidence-box");
  child(el, "h3", "", title);
  return el;
}
function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.hidden = true; }, 5000);
}
async function api(path, body) {
  const options = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
async function act(path, body, chatCall = false) {
  if (busy) return;
  busy = true;
  if (chatCall) {
    pendingMessage = body.message;
    renderChat();
    waitingSince = Date.now();
    $("chatStatus").textContent = "Thinking…";
    timer = setInterval(() => { $("chatStatus").textContent = `Thinking… ${Math.floor((Date.now() - waitingSince) / 1000)}s`; }, 500);
  }
  renderBusy();
  try {
    state = await api(path, body);
    pendingMessage = null;
    render();
  } catch (error) {
    if (chatCall) {
      $("messageInput").value = body.message;
      pendingMessage = null;
      renderChat();
    }
    toast(error.message);
  } finally {
    busy = false;
    clearInterval(timer);
    $("chatStatus").textContent = "";
    renderBusy();
  }
}
function renderBusy() {
  const chat = state?.conversation;
  $("sendButton").disabled = busy || !chat || !!chat.stopped;
  for (const id of ["directButton", "continueButton", "signoutButton"]) $(id).disabled = busy;
  document.querySelectorAll(".campaign-card button").forEach(button => { button.disabled = busy; });
}
function renderCampaigns() {
  const grid = $("campaignGrid");
  grid.replaceChildren();
  const selectedCountry = $("countrySelect").value;
  for (const [index, campaign] of state.campaigns.entries()) {
    const details = cardInfo[campaign.card];
    const offerOnly = Boolean(campaign.country_restriction && campaign.country_restriction !== selectedCountry);
    const card = child(grid, "article", "campaign-card");
    const top = child(card, "div", "card-top");
    child(top, "div", "card-icon", details.icon);
    child(top, "span", "card-index", `0${index + 1} / 04`);
    child(card, "h3", "", campaign.card);
    child(card, "span", "audience", details.audience);
    child(card, "p", "", details.benefit);
    child(card, "span", "entry-context", offerOnly ? "Featured card" : "Campaign offer");
    const button = child(card, "button", "", "Explore this offer");
    button.type = "button";
    child(button, "span", "", "→");
    button.disabled = busy;
    button.addEventListener("click", () => offerOnly ? openLogin("offer", null, campaign.card) : openLogin("campaign", campaign.id));
  }
}
function renderSteps(chat) {
  const steps = [
    ["Entry chosen", true],
    ["Demo customer selected", !!chat.demo_alias],
    ["Suggestion available", state.last_result?.route === "POLICY_SUGGESTION" || state.events.some(e => e.route === "POLICY_SUGGESTION")],
    ["Simulated precheck", Object.keys(state.prechecks || {}).length > 0],
    ["Application recorded", !!state.application]
  ];
  const holder = $("journeySteps");
  holder.replaceChildren();
  steps.forEach(([label, done], i) => {
    const step = child(holder, "div", `step${done ? " done" : ""}`);
    child(step, "span", "step-num", done ? "✓" : String(i + 1));
    child(step, "span", "", label);
  });
}
function renderAccount(chat) {
  $("selectedPersona").textContent = `${chat.demo_alias} · ${state.personas.find(p => p.alias === chat.demo_alias)?.segment || "Customer"} · ${chat.country}`;
  $("messageInput").disabled = chat.stopped;
  $("messageInput").placeholder = chat.stopped ? "Conversation ended. Choose another journey to continue." : state.chat_available ? "Ask about benefits, fees, or how a card works…" : "Product answers are temporarily unavailable. Card requests and local prechecks still work.";
}
function openLogin(entry, campaignId = null, selectedCard = null) {
  pendingEntry = {entry, campaign_id: campaignId, selected_card: selectedCard, country: $("countrySelect").value, language: $("languageSelect").value};
  const choices = state.personas.filter(p => p.country === pendingEntry.country);
  const select = $("loginPersonaSelect");
  select.replaceChildren();
  for (const p of choices) {
    const option = node("option", "", `${p.alias} · ${p.segment} · ${p.country}`);
    option.value = p.alias;
    select.append(option);
  }
  $("loginContext").textContent = entry === "campaign" ? `Continue to explore ${state.campaigns.find(c => c.id === campaignId).card}.` : entry === "offer" ? `Continue to explore ${selectedCard}.` : "Continue to explore our credit cards.";
  render();
  loadPreview();
}
async function loadPreview() {
  const request = ++previewRequest;
  const alias = $("loginPersonaSelect").value;
  const holder = $("loginPreview");
  holder.replaceChildren();
  child(holder, "p", "muted", "Loading customer profile…");
  $("continueButton").disabled = true;
  try {
    const {persona: p} = await api("/api/persona-preview", {alias});
    if (request !== previewRequest || alias !== $("loginPersonaSelect").value) return;
    holder.replaceChildren();
    row(holder, "Country", p.country);
    row(holder, "City / state", `${p.city}, ${p.state}`);
    row(holder, "Customer segment", p.segment);
    row(holder, "Account status", p.customer_status);
    row(holder, "Occupation", p.occupation);
    row(holder, "Credit score", p.credit_score);
    row(holder, "Estimated monthly income", p.estimated_monthly_income == null ? "Unavailable" : `${p.income_currency} ${Number(p.estimated_monthly_income).toLocaleString()}`);
    row(holder, "Approx. monthly income (USD)", p.estimated_monthly_income_usd == null ? "Unavailable" : `USD ${Number(p.estimated_monthly_income_usd).toLocaleString()}`);
    row(holder, "Current credit card", p.has_current_credit_card ? "Yes" : "No");
    if (p.usd_rate_date) child(holder, "p", "quiet-note", `USD estimate uses the last available historical ${p.income_currency}→USD rate (${p.usd_rate_date}); it is not a current conversion.`);
    else child(holder, "p", "quiet-note", "This team-generated profile has no USD estimate or live exchange-rate quote.");
    $("continueButton").disabled = busy;
  } catch (error) {
    if (request === previewRequest) { holder.replaceChildren(); toast(error.message); }
  }
}
function renderChat() {
  const holder = $("chatMessages");
  holder.replaceChildren();
  for (const event of [...state.events, ...(pendingMessage ? [{role: "user", text: pendingMessage, pending: true}] : [])]) {
    const wrapper = child(holder, "div", `message ${event.role}`);
    child(wrapper, "div", "message-avatar", event.role === "user" ? "U" : "✳");
    const content = child(wrapper, "div", "");
    child(content, "div", `bubble${event.pending ? " pending" : ""}`, event.text);
    if (event.role === "assistant" && event.citations?.length) child(content, "div", "message-meta", `Sources: ${event.citations.join(" · ")}`);
  }
  holder.scrollTop = holder.scrollHeight;
  const chips = $("promptChips");
  chips.replaceChildren();
  const lang = state.conversation.language;
  for (const suggestion of prompts[lang]) {
    const button = child(chips, "button", "prompt-chip", suggestion);
    button.type = "button";
    button.addEventListener("click", () => { $("messageInput").value = suggestion; $("messageInput").focus(); });
  }
}
function renderEvidence(chat) {
  const holder = $("evidenceContent");
  holder.replaceChildren();
  const entry = box(holder, "Entry context");
  row(entry, "Path", chat.entry_kind === "campaign" ? "Campaign click" : chat.entry_kind === "offer" ? "Direct offer exploration" : "Direct visit");
  row(entry, "Country", chat.country || "Unknown");
  row(entry, "Chat language", chat.language === "es" ? "Spanish" : "Portuguese");
  if (chat.campaign_id) { row(entry, "Source campaign", chat.campaign_id); row(entry, "Mapped demo offer", state.campaigns.find(c => c.id === chat.campaign_id)?.card); }
  row(entry, "Current card", chat.selected_card || "None selected");
  child(entry, "p", "", chat.campaign_id ? "The source campaign is historical. This click and named-card mapping were created for this demo." : "No campaign or prior click is assumed.");
  const profile = box(holder, "Customer profile");
  row(profile, "Selected fixture", chat.demo_alias || "None");
  if (state.profile) {
    row(profile, "Segment", state.profile.segment);
    row(profile, "Stored score", state.profile.credit_score);
    row(profile, "Est. monthly income", `${state.profile.income_currency} ${state.profile.estimated_monthly_income ?? "unavailable"}`);
    row(profile, "Current credit card", state.profile.has_current_credit_card ? "Yes" : "No");
    child(profile, "p", "", state.profile.source === "TEAM_GENERATED_DEMO_FIXTURE" ? "Team-generated test profile. Values are fictional and not verified live income or score." : "Organizer-synthetic current snapshot. Stored values are not verified live income or score.");
  }
  if (Object.keys(state.prechecks || {}).length) {
    const checks = box(holder, "Simulated precheck");
    for (const [card, status] of Object.entries(state.prechecks)) row(checks, card, status.replaceAll("_", " "));
  }
  const result = box(holder, "Latest decision / answer");
  if (state.last_result) {
    row(result, "Route", state.last_result.route);
    if (state.last_result.policy) {
      const p = state.last_result.policy;
      child(result, "span", "status-tag", p.status.replaceAll("_", " "));
      row(result, "Card", p.card || "None");
      row(result, "Policy", p.policy_version);
      row(result, "Offer", p.offer_version);
      if (p.reasons?.length) row(result, "Reasons", p.reasons.join(", "));
    } else if (state.last_result.citations?.length) row(result, "Fact IDs", state.last_result.citations.join(", "));
  } else child(result, "p", "", "A product answer, card suggestion, or precheck result will appear here.");
  const safety = box(holder, "Decision boundary");
  child(safety, "p", "", "Card terms and thresholds are synthetic. A suggested card is for discussion; a precheck is not an approval. Confirmed applications and human requests are local mock records pending review. No human assignment is created yet.");
  const application = box(holder, "Mock application");
  if (state.application) {
    row(application, "Reference", state.application.application_id);
    row(application, "Card", state.application.card);
    row(application, "Status", state.application.status);
    row(application, "Precheck", state.application.precheck_status || "Not run");
    row(application, "Offer version", state.application.offer_version);
  } else if (state.application_draft) {
    row(application, "Card", state.application_draft.card);
    row(application, "State", "Waiting for explicit confirmation");
    row(application, "Precheck", state.application_draft.precheck_status || "Not run");
  } else child(application, "p", "", "No application has been prepared or recorded.");
  const handoff = box(holder, "Human request");
  if (state.handoff) {
    row(handoff, "Reference", state.handoff.handoff_id);
    row(handoff, "Status", state.handoff.status);
    row(handoff, "Assigned employee", "None");
  } else child(handoff, "p", "", "No human request has been recorded.");
}
function render() {
  if (!state) return;
  document.querySelector(".review-link").hidden = !state.review_available;
  const chat = state.conversation;
  $("landing").hidden = !!chat || !!pendingEntry;
  $("login").hidden = !!chat || !pendingEntry;
  $("workspace").hidden = !chat;
  $("homeButton").hidden = !chat && !pendingEntry;
  if (!chat) { if (!pendingEntry) renderCampaigns(); renderBusy(); return; }
  pendingEntry = null;
  $("journeyTitle").textContent = chat.selected_card ? `Explore ${chat.selected_card}` : "Explore the cards";
  $("journeySubtitle").textContent = chat.entry_kind === "campaign" ? "From a card campaign." : chat.entry_kind === "offer" ? "Exploring a featured card." : "Started without a campaign.";
  renderSteps(chat);
  renderAccount(chat);
  renderChat();
  renderEvidence(chat);
  renderBusy();
}
$("countrySelect").addEventListener("change", () => { if (state) renderCampaigns(); });
$("directButton").addEventListener("click", () => openLogin("direct"));
$("homeButton").addEventListener("click", async () => { if (busy) return; pendingEntry = null; ++previewRequest; await act("/api/home", {}); });
$("loginPersonaSelect").addEventListener("change", loadPreview);
$("continueButton").addEventListener("click", () => act("/api/start", {...pendingEntry, alias: $("loginPersonaSelect").value}));
$("signoutButton").addEventListener("click", () => act("/api/home", {}));
$("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("messageInput");
  const message = input.value.trim();
  if (!message || busy) return;
  input.value = "";
  await act("/api/chat", {message}, true);
});
$("messageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("chatForm").requestSubmit(); }
});
api("/api/state").then(data => { state = data; render(); }).catch(error => toast(error.message));
