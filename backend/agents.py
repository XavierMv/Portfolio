"""
agents.py  –  AI Agent Engine
Calls Anthropic claude-sonnet-4-20250514 with web search to analyze portfolios.
Each agent has a role, system prompt, and returns structured JSON.
"""
import os
import json
import anthropic
from datetime import date

def _clean_key() -> str:
    """Read the key from env and strip stray quotes/whitespace (the .env.example
    template ships with a leading quote, a common copy-paste trap)."""
    k = os.environ.get("ANTHROPIC_API_KEY", "") or ""
    return k.strip().strip('"').strip("'").strip()

# Current model string; override with ANTHROPIC_MODEL in .env if unavailable.
MODEL = (os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-4-5")

def _client():
    return anthropic.Anthropic(api_key=_clean_key())

def _create_with_retry(**kwargs):
    """Call messages.create with one automatic retry on 429 (Tier-1 rate limits).
    Honors the Retry-After header when present."""
    import time
    try:
        return _client().messages.create(**kwargs)
    except anthropic.RateLimitError as e:
        wait = 20
        try:
            ra = e.response.headers.get("retry-after")
            if ra:
                wait = min(int(float(ra)) + 1, 40)
        except Exception:
            pass
        time.sleep(wait)
        return _client().messages.create(**kwargs)

TODAY = date.today().isoformat()

AGENT_DEFS = [
    {
        "id":    "macro",
        "icon":  "🌐",
        "name":  "Macro Agent",
        "role":  "Macro & Interest Rate Analyst",
        "color": "#00ccf5",
        "system": (
            "You are an expert macro economist and portfolio strategist. "
            "Analyze how current macroeconomic conditions (Fed policy, interest rates, "
            "inflation, USD strength, global growth) affect the given portfolio. "
            "Use web search to find the latest data. Be specific with numbers and dates. "
            "Return ONLY valid JSON, no markdown."
        ),
    },
    {
        "id":    "sector",
        "icon":  "🏭",
        "name":  "Sector Agent",
        "role":  "Thematic & Sector Rotation Analyst",
        "color": "#1ddb82",
        "system": (
            "You are a sector rotation and thematic investing specialist. "
            "Analyze each theme in the portfolio (AI, Nuclear, Space, LNG, Robotics, Quantum) "
            "for institutional flows, regulatory tailwinds/headwinds, earnings trends, and "
            "sector rotation signals. Use web search for the latest news. "
            "Return ONLY valid JSON, no markdown."
        ),
    },
    {
        "id":    "risk",
        "icon":  "🛡️",
        "name":  "Risk Agent",
        "role":  "Portfolio Risk & Tail Risk Analyst",
        "color": "#ff3558",
        "system": (
            "You are a quantitative risk manager specializing in portfolio tail risk. "
            "Analyze drawdown risk, concentration risk, correlation risk, and specific "
            "position risks in the given portfolio. Identify the biggest risk factors "
            "and provide concrete mitigation strategies. "
            "Return ONLY valid JSON, no markdown."
        ),
    },
    {
        "id":    "news",
        "icon":  "📰",
        "name":  "News Agent",
        "role":  "Real-Time News & Catalyst Scanner",
        "color": "#9933ff",
        "system": (
            "You are a financial news analyst and catalyst scanner. "
            "Search for the latest news, earnings, regulatory changes, and catalysts "
            "for the stocks in the portfolio. Focus on events from the past 30 days. "
            "Identify bullish and bearish catalysts for each major position. "
            "Return ONLY valid JSON, no markdown."
        ),
    },
    {
        "id":    "quant",
        "icon":  "🤖",
        "name":  "Quant Agent",
        "role":  "Quantitative Strategy & Factor Model",
        "color": "#ffaa18",
        "system": (
            "You are a quantitative portfolio strategist. "
            "Analyze the portfolio's factor exposures (momentum, quality, value, beta), "
            "identify which stocks are helping vs hurting performance, "
            "and recommend specific weight adjustments to improve the Sharpe ratio. "
            "Return ONLY valid JSON, no markdown."
        ),
    },
]

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["sentiment", "summary", "bullets", "recommendation"],
    "properties": {
        "sentiment": {"type": "string", "enum": ["BULLISH", "CAUTIOUS", "BEARISH", "HIGH RISK", "MIXED", "OPPORTUNISTIC"]},
        "summary":   {"type": "string"},
        "bullets":   {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["icon", "text", "color"],
                "properties": {
                    "icon":  {"type": "string"},
                    "text":  {"type": "string"},
                    "color": {"type": "string"},
                }
            }
        },
        "recommendation": {"type": "string"},
    }
}

SENTIMENT_COLORS = {
    "BULLISH":       "#1ddb82",
    "CAUTIOUS":      "#ffaa18",
    "BEARISH":       "#ff3558",
    "HIGH RISK":     "#ff3558",
    "MIXED":         "#ffaa18",
    "OPPORTUNISTIC": "#00ccf5",
}

def _build_prompt(agent_id: str, portfolio_summary: dict) -> str:
    tickers    = portfolio_summary.get("tickers", [])
    themes     = portfolio_summary.get("themes", {})
    port_stats = portfolio_summary.get("portfolio_stats", {})

    ticker_str = ", ".join(tickers[:20])
    theme_str  = ", ".join(f"{k}:{v}" for k, v in themes.items())

    base = f"""
Today is {TODAY}.

Portfolio: {ticker_str}
Themes: {theme_str}
Portfolio Sharpe: {port_stats.get('sharpe', 'N/A')}
Portfolio Ann. Return: {port_stats.get('annualized_return', 'N/A')}
Portfolio Volatility: {port_stats.get('annualized_volatility', 'N/A')}
Portfolio Beta: {port_stats.get('beta', 'N/A')}
Portfolio Max Drawdown: {port_stats.get('max_drawdown', 'N/A')}

You have COMPLETE portfolio information above (holdings, themes, and risk/return stats).
Analyze EXACTLY these holdings. NEVER ask the user for more data or clarification —
if web search is unavailable, reason from the data above and your own knowledge.
"""

    prompts = {
        "macro": base + "\nAnalyze how current macro conditions affect this portfolio. Search for latest Fed statements, CPI data, and yield curve data.",
        "sector": base + "\nAnalyze sector rotation signals and thematic tailwinds/headwinds for each theme in this portfolio. Search for latest news per theme.",
        "risk": base + "\nIdentify the top risk factors for this portfolio. Analyze concentration, correlation, and tail risks. Give specific risk metrics and mitigation actions.",
        "news": base + "\nSearch for the latest news (past 30 days) on the top 10 holdings. Identify the most important bullish and bearish catalysts.",
        "quant": base + "\nAnalyze factor exposures and quantitative signals. Identify which stocks to increase/decrease weight for maximum Sharpe improvement.",
    }
    contract = """

OUTPUT CONTRACT — Reply with ONE JSON object and NOTHING else. No preamble,
no narration ("I'll analyze…", "Let me search…"), no markdown fences, no <cite>
tags, no URLs, no extra keys. Keep it tight so it fits in the response.
Exact shape:
{
  "sentiment": "one of: BULLISH | CAUTIOUS | BEARISH | HIGH RISK | MIXED | OPPORTUNISTIC",
  "summary": "2-4 plain-text sentences. Weave any researched figures inline as plain text.",
  "bullets": [
    {"icon": "single emoji", "text": "one concise finding in plain text", "color": "#1ddb82 (green=good) | #ffaa18 (amber=watch) | #ff3558 (red=risk) | #00ccf5 (cyan=info)"}
  ],
  "recommendation": "1-2 plain-text sentences with a concrete action."
}
Provide 3 to 5 bullets. Do NOT include citation markup of any kind."""
    return prompts.get(agent_id, base) + contract


import re as _re

def _strip_cites(obj):
    """Remove <cite ...>…</cite> markup (and stray tags) that the web-search
    tool injects, recursively across all string values in the report."""
    if isinstance(obj, str):
        return _re.sub(r"</?cite[^>]*>", "", obj).strip()
    if isinstance(obj, list):
        return [_strip_cites(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _strip_cites(v) for k, v in obj.items()}
    return obj

def _extract_json(text: str):
    """Pull a JSON object out of model text that may include citations, prose,
    or ```json fences (web-search responses rarely return bare JSON)."""
    if not text:
        return None
    t = text.strip()
    m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, _re.DOTALL)
    if m:
        t = m.group(1)
    start = t.find("{")
    if start == -1:
        return None
    # walk to the matching closing brace
    depth, out = 0, []
    for ch in t[start:]:
        out.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    frag = "".join(out)
    try:
        return json.loads(frag)
    except Exception:
        try:
            return json.loads(t[start:t.rfind("}") + 1])
        except Exception:
            return None


def run_agent(agent_id: str, portfolio_summary: dict) -> dict:
    """
    Run a single AI agent. Returns the agent definition + report dict.
    Falls back to a rich static report if the API key is missing.
    """
    agent = next((a for a in AGENT_DEFS if a["id"] == agent_id), None)
    if agent is None:
        return {"error": f"Unknown agent: {agent_id}"}

    api_key = _clean_key()
    if not api_key or api_key == "your-key-here":
        return {**agent, "report": _fallback_report(agent_id, portfolio_summary), "live": False}

    prompt = _build_prompt(agent_id, portfolio_summary)

    def _valid(rep):
        return (isinstance(rep, dict) and rep.get("sentiment") and rep.get("summary")
                and isinstance(rep.get("bullets"), list) and len(rep["bullets"]) > 0)

    def _finalize(rep):
        rep = _strip_cites(rep)
        if not isinstance(rep.get("bullets"), list):
            rep["bullets"] = []
        rep["summary"] = str(rep.get("summary", "") or "")
        rep["recommendation"] = str(rep.get("recommendation", "") or "")
        rep["sentiment_color"] = SENTIMENT_COLORS.get(rep.get("sentiment", "MIXED"), "#ffaa18")
        return rep

    text = ""
    try:
        # ── Pass 1: live web search ──────────────────────────────────────────
        resp = _create_with_retry(
            model=MODEL, max_tokens=2000, system=agent["system"],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        report = _extract_json(text)

        # ── Pass 2: repair — force clean JSON if pass 1 was chatty, asked a
        #    question, or returned the wrong shape. No tools + assistant prefill.
        if not _valid(report):
            resp2 = _create_with_retry(
                model=MODEL, max_tokens=1500, system=agent["system"],
                messages=[
                    {"role": "user", "content": prompt +
                     "\n\nThe portfolio above is COMPLETE. Do NOT ask for holdings or any "
                     "other information. Output ONLY the JSON object described, starting now."},
                    {"role": "assistant", "content": "{"},
                ],
            )
            text2 = "{" + "".join(b.text for b in resp2.content if hasattr(b, "text"))
            report = _extract_json(text2) or report

        if not _valid(report):
            clean = _re.sub(r"</?cite[^>]*>", "", text or "").strip()
            report = {"sentiment": "MIXED",
                      "summary": (clean[:1200] or "Model returned no usable content."),
                      "bullets": [], "recommendation": ""}
        return {**agent, "report": _finalize(report), "live": True}

    except anthropic.RateLimitError:
        rep = _fallback_report(agent_id, portfolio_summary)
        rep["_error"] = ("Rate limited (Tier 1 = 30k input tokens/min). Web search is "
                         "token-heavy — wait ~60s and rerun, or add credits to reach Tier 2.")
        return {**agent, "report": rep, "live": False}
    except Exception as e:
        print(f"[Agent {agent_id}] API error: {e} — using fallback")
        rep = _fallback_report(agent_id, portfolio_summary)
        rep["_error"] = f"{type(e).__name__}: {e}"
        return {**agent, "report": rep, "live": False}

def _fallback_report(agent_id: str, portfolio_summary: dict) -> dict:
    """Rich static reports shown when no API key is configured."""
    tickers = portfolio_summary.get("tickers", [])
    stats   = portfolio_summary.get("portfolio_stats", {})
    sh  = stats.get("sharpe",  "N/A")
    ret = stats.get("annualized_return", "N/A")
    vol = stats.get("annualized_volatility", "N/A")
    bta = stats.get("beta", "N/A")
    mdd = stats.get("max_drawdown", "N/A")

    def fmt(v):
        if isinstance(v, float):
            return f"{v*100:.1f}%"
        return str(v)

    reports = {
        "macro": {
            "sentiment": "CAUTIOUS",
            "summary": (
                f"This portfolio (Sharpe {fmt(sh)}, beta {fmt(bta)}) carries significant macro sensitivity. "
                "Fed higher-for-longer policy through mid-2025 creates headwinds for high-multiple growth names "
                "in AI and Quantum. Nuclear and LNG holdings benefit from energy inflation and structural demand. "
                "Watch 10Y Treasury yields — sustained moves above 4.8% will compress AI/Quantum multiples."
            ),
            "bullets": [
                {"icon":"⚠️","text":f"Portfolio beta {fmt(bta)} amplifies market moves by {fmt(bta)} — high rate sensitivity","color":"#ffaa18"},
                {"icon":"✅","text":"Nuclear stocks (CEG, VST) have inflation-linked PPAs — natural rate hedge","color":"#1ddb82"},
                {"icon":"⚠️","text":"AI/Quantum P/E multiples near 2021 peaks — vulnerable to rate re-pricing","color":"#ff3558"},
                {"icon":"✅","text":"LNG exports structural tailwind — EU energy crisis drove long-term contracts through 2030","color":"#1ddb82"},
            ],
            "recommendation": f"Reduce high-beta Quantum positions (IONQ, QBTS). Overweight Nuclear + LNG as rate-resistant compounders. Target portfolio beta below 1.2.",
            "sentiment_color": "#ffaa18",
        },
        "sector": {
            "sentiment": "BULLISH",
            "summary": (
                "Nuclear and AI infrastructure themes are entering multi-year institutional adoption cycles. "
                "The ADVANCE Act accelerates SMR permitting. Hyperscaler AI capex growing 40%+ YoY directly "
                "benefits NVDA and AVGO. Robotics facing near-term enterprise budget tightening. "
                "Space bifurcating — defense primes stable, pure-plays volatile and cash-burning."
            ),
            "bullets": [
                {"icon":"🚀","text":"Nuclear: ADVANCE Act signed — accelerates NRC licensing. Direct catalyst for OKLO, SMR, BWXT","color":"#1ddb82"},
                {"icon":"🚀","text":"AI infrastructure: hyperscaler capex +40% YoY — NVDA Blackwell demand exceeds supply through 2025","color":"#1ddb82"},
                {"icon":"⚠️","text":"Robotics: enterprise automation capex tightening — SYM and PATH facing elongated sales cycles","color":"#ffaa18"},
                {"icon":"⚠️","text":"Space pure-plays (RKLB, LUNR, PL) burning cash — monitor quarterly burn vs backlog ratio","color":"#ff3558"},
            ],
            "recommendation": "Overweight Nuclear + AI. Trim Robotics drag (PATH, ROK). Hold Space defense primes (LMT, NOC). Add BWXT on nuclear legislation catalyst.",
            "sentiment_color": "#1ddb82",
        },
        "risk": {
            "sentiment": "HIGH RISK",
            "summary": (
                f"Portfolio carries elevated tail risk: VaR 95% annualized exceeds 55%, max drawdown {fmt(mdd)}. "
                "Several positions (PL, PATH, ROK) have negative Sharpe ratios and act as return drag. "
                "Correlation spikes to 0.82 in drawdowns — diversification benefit largely disappears in crashes. "
                "Position sizing is equal-weight which overweights speculative names relative to their alpha contribution."
            ),
            "bullets": [
                {"icon":"🔴","text":"HIGH: PL (-44% ann.), PATH (-18%, neg-alpha), ROK (-9%) — immediate review required","color":"#ff3558"},
                {"icon":"🔴","text":f"Portfolio max drawdown {fmt(mdd)} — requires 3-5Y commitment to recover from worst case","color":"#ff3558"},
                {"icon":"⚠️","text":"Correlation rises to 0.82 during market stress — diversification disappears in crashes","color":"#ffaa18"},
                {"icon":"✅","text":"LMT, NOC, IBM, XOM, KMI provide low-beta stabilization — increase weights for risk reduction","color":"#1ddb82"},
            ],
            "recommendation": "Exit PL, PATH immediately. Reduce QBTS, IONQ to <1.5%. Increase LMT, NOC, XOM to 5%+ each. Target portfolio vol below 30%.",
            "sentiment_color": "#ff3558",
        },
        "news": {
            "sentiment": "MIXED",
            "summary": (
                "Active catalysts across all 6 themes. Nuclear legislation creating positive momentum "
                "for the sector. AI export controls creating near-term uncertainty for NVDA and ASML. "
                "Space defense contracts accelerating post-conflict geopolitical spending. "
                "LNG permitting faces regulatory review delays. Quantum commercial timelines extending."
            ),
            "bullets": [
                {"icon":"🔥","text":"NUCLEAR: ADVANCE Act signed — accelerates SMR licensing. Buy signal for OKLO, SMR, BWXT, CEG","color":"#1ddb82"},
                {"icon":"⚠️","text":"AI: BIS export controls on advanced AI chips — NVDA China revenue at risk, ASML booking delays","color":"#ff3558"},
                {"icon":"🔥","text":"SPACE: DoD $2.4B satellite constellation shortlist includes RKLB, NOC, LMT — contract award imminent","color":"#1ddb82"},
                {"icon":"⚠️","text":"QUANTUM: IBM roadmap slipped 12 months — commercial quantum advantage now 2028+ per management","color":"#ff3558"},
            ],
            "recommendation": "Buy on catalyst: BWXT, OKLO (nuclear legislation). Monitor NVDA export control news weekly. Hold RKLB ahead of DoD contract award.",
            "sentiment_color": "#ffaa18",
        },
        "quant": {
            "sentiment": "OPPORTUNISTIC",
            "summary": (
                f"Factor analysis reveals this portfolio loads heavily on momentum (68%) and quality (22%) factors "
                f"with near-zero defensive exposure. Current Sharpe {fmt(sh)} vs optimized {fmt(sh)+' → ~1.88' if isinstance(sh,float) else '→ ~1.88'}. "
                "Max Sharpe optimization shifts ~28% weight from bottom-quintile stocks (PL, PATH, ROK, EWY) "
                "to top-quintile compounders (VST, CEG, NVDA, LNG). Expected improvement: +8.1% return, -14.4% vol."
            ),
            "bullets": [
                {"icon":"📊","text":"Factor exposure: 68% momentum, 22% quality, 10% value — nearly zero defensive loading","color":"#00ccf5"},
                {"icon":"✅","text":"Max Sharpe optimization: +8.1% return, -14.4% vol, +0.74 Sharpe vs equal-weight","color":"#1ddb82"},
                {"icon":"📊","text":"Bottom 5 risk-adjusted contributors: PL, PATH, ROK, EWY, QBTS — all candidates for reduction","color":"#ffaa18"},
                {"icon":"✅","text":"Top 5 alpha contributors: VST, CEG, NVDA, RKLB, CCJ — increase weights here for best impact","color":"#1ddb82"},
            ],
            "recommendation": "Run Max Sharpe optimization via the Optimizer tab. Target: +8% return, -14% vol, +0.74 Sharpe improvement. Rebalance quarterly.",
            "sentiment_color": "#00ccf5",
        },
    }
    return reports.get(agent_id, {"sentiment":"MIXED","summary":"Analysis unavailable.","bullets":[],"recommendation":"","sentiment_color":"#ffaa18"})


def get_agent_list() -> list[dict]:
    """Return agent definitions without reports (for the UI to show cards)."""
    return [{"id":a["id"],"icon":a["icon"],"name":a["name"],"role":a["role"],"color":a["color"]}
            for a in AGENT_DEFS]


# ════════════════════════════════════════════════════════════════════════════
# Scout / Discovery agent — discovers NET-NEW tickers in a theme (not analysis)
# ════════════════════════════════════════════════════════════════════════════
SCOUT_STEP_LABELS = [
    "Mapping the theme value chain…",
    "Searching for peers & challengers…",
    "Screening supply-chain / picks-and-shovels names…",
    "Applying hard constraints (no Taiwan/OTC/China/crypto)…",
    "Compiling candidate list…",
]

_SCOUT_CONSTRAINTS = (
    "HARD CONSTRAINTS — apply BEFORE returning any name: "
    "(1) NO Taiwan-listed stocks; (2) NO OTC / pink-sheet securities; "
    "(3) NO mainland-China-domiciled names; (4) NO crypto-adjacent names "
    "(miners, exchanges, treasury-coin proxies); (5) PREFER NASDAQ / NYSE / TSX "
    "primary listings; (6) use the EWY ETF for Korean exposure instead of KRX listings; "
    "(7) if Wealthsimple availability is uncertain, set wealthsimple_uncertain=true."
)

# Curated seed candidates per theme — shown when no API key (static fallback).
_SCOUT_SEEDS = {
    "AI": [
        {"ticker":"ARM","name":"Arm Holdings","exchange":"NASDAQ","theme":"AI","one_line_thesis":"CPU IP royalty/platform that wins regardless of which chipmaker leads.","model_type":"royalty/platform","wealthsimple_uncertain":False},
        {"ticker":"MU","name":"Micron Technology","exchange":"NASDAQ","theme":"AI","one_line_thesis":"HBM memory supplier riding AI accelerator demand.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"KLAC","name":"KLA Corporation","exchange":"NASDAQ","theme":"AI","one_line_thesis":"Process-control toolmaker — picks-and-shovels for every leading-edge fab.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"SNPS","name":"Synopsys","exchange":"NASDAQ","theme":"AI","one_line_thesis":"EDA software duopoly — every advanced chip is designed on it.","model_type":"royalty/platform","wealthsimple_uncertain":False},
        {"ticker":"MRVL","name":"Marvell Technology","exchange":"NASDAQ","theme":"AI","one_line_thesis":"Custom AI silicon and optical interconnect for hyperscalers.","model_type":"pure-play","wealthsimple_uncertain":False},
    ],
    "Nuclear": [
        {"ticker":"SMR","name":"NuScale Power","exchange":"NYSE","theme":"Nuclear","one_line_thesis":"Leading US SMR design with NRC-certified module.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"LEU","name":"Centrus Energy","exchange":"NYSE","theme":"Nuclear","one_line_thesis":"Only US-owned HALEU enrichment — fuel supply pick-and-shovel.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"UEC","name":"Uranium Energy","exchange":"NYSE","theme":"Nuclear","one_line_thesis":"US-focused in-situ uranium miner leveraged to spot price.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"NXE","name":"NexGen Energy","exchange":"NYSE/TSX","theme":"Nuclear","one_line_thesis":"Tier-1 Athabasca uranium development (Arrow deposit).","model_type":"pure-play","wealthsimple_uncertain":False},
    ],
    "Space": [
        {"ticker":"KTOS","name":"Kratos Defense","exchange":"NASDAQ","theme":"Space","one_line_thesis":"Drones, propulsion and space systems for the DoD.","model_type":"diversified","wealthsimple_uncertain":False},
        {"ticker":"RDW","name":"Redwire","exchange":"NYSE","theme":"Space","one_line_thesis":"Space infrastructure components — picks-and-shovels for orbit.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"HEI","name":"HEICO","exchange":"NYSE","theme":"Space","one_line_thesis":"Aerospace parts compounder with defense/space exposure.","model_type":"diversified","wealthsimple_uncertain":False},
    ],
    "LNG": [
        {"ticker":"WMB","name":"Williams Companies","exchange":"NYSE","theme":"LNG","one_line_thesis":"US gas pipeline backbone feeding LNG export terminals.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"OKE","name":"ONEOK","exchange":"NYSE","theme":"LNG","one_line_thesis":"NGL & gas midstream toll-road model.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"CQP","name":"Cheniere Energy Partners","exchange":"NYSE","theme":"LNG","one_line_thesis":"Sabine Pass LNG cash-flow vehicle.","model_type":"pure-play","wealthsimple_uncertain":True},
    ],
    "Quantum": [
        {"ticker":"RGTI","name":"Rigetti Computing","exchange":"NASDAQ","theme":"Quantum","one_line_thesis":"Superconducting-qubit pure-play with own fab.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"QUBT","name":"Quantum Computing Inc","exchange":"NASDAQ","theme":"Quantum","one_line_thesis":"Photonic quantum + thin-film lithium niobate foundry.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"HON","name":"Honeywell","exchange":"NASDAQ","theme":"Quantum","one_line_thesis":"Quantinuum stake — diversified industrial exposure to quantum.","model_type":"diversified","wealthsimple_uncertain":False},
    ],
    "Robotics": [
        {"ticker":"ZBRA","name":"Zebra Technologies","exchange":"NASDAQ","theme":"Robotics","one_line_thesis":"Warehouse automation, scanning and machine vision.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"SERV","name":"Serve Robotics","exchange":"NASDAQ","theme":"Robotics","one_line_thesis":"Autonomous sidewalk delivery robots — speculative pure-play.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"NVMI","name":"Nova Ltd","exchange":"NASDAQ","theme":"Robotics","one_line_thesis":"Automation/metrology supplier (Israel-listed, NASDAQ primary).","model_type":"supply-chain","wealthsimple_uncertain":True},
    ],
    "AR": [
        {"ticker":"VUZI","name":"Vuzix","exchange":"NASDAQ","theme":"AR","one_line_thesis":"Enterprise smart-glasses and waveguide optics pure-play.","model_type":"pure-play","wealthsimple_uncertain":False},
        {"ticker":"KOPN","name":"Kopin","exchange":"NASDAQ","theme":"AR","one_line_thesis":"Microdisplay supplier for AR/VR headsets and defense.","model_type":"supply-chain","wealthsimple_uncertain":False},
        {"ticker":"SONY","name":"Sony Group","exchange":"NYSE","theme":"AR","one_line_thesis":"OLED microdisplays + content — diversified AR exposure.","model_type":"diversified","wealthsimple_uncertain":False},
    ],
}


def _static_scout(theme: str, owned: list) -> dict:
    base = theme.split("/")[0].strip()
    seeds = _SCOUT_SEEDS.get(theme) or _SCOUT_SEEDS.get(base) or []
    cands = [c for c in seeds if c["ticker"].upper() not in owned]
    return {"candidates": cands,
            "note": "Static curated seeds (no API key configured — add one for live web-search discovery)."}


def run_scout(theme: str, owned_tickers=None) -> dict:
    """Discover net-new tickers in a theme. Live web search with key; static seeds otherwise."""
    owned = [t.upper() for t in (owned_tickers or [])]
    api_key = _clean_key()
    if not api_key or api_key == "your-key-here":
        return {"report": _static_scout(theme, owned), "live": False}

    system = (
        "You are an equity-research discovery scout for a Canadian retail investor on Wealthsimple. "
        "Map the value chain of the given theme and surface NET-NEW tickers — peers, challengers, and "
        "supply-chain / picks-and-shovels names beyond the obvious large caps the investor already owns. "
        + _SCOUT_CONSTRAINTS +
        ' Return ONLY valid JSON (no markdown, no preamble) of the exact form: '
        '{"candidates":[{"ticker":"","name":"","exchange":"","theme":"","one_line_thesis":"",'
        '"model_type":"","wealthsimple_uncertain":false}]}. '
        "model_type must be one of: royalty/platform, pure-play, supply-chain, diversified."
    )
    prompt = (f"Theme: {theme}\n"
              f"Already owned (exclude these): {', '.join(owned) or 'none'}\n"
              f"Return 6-10 net-new candidates that pass all hard constraints.")
    try:
        resp = _create_with_retry(
            model=MODEL, max_tokens=1500, system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for b in resp.content:
            if hasattr(b, "text"):
                text += b.text
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        cands = [c for c in data.get("candidates", [])
                 if c.get("ticker", "").upper() not in owned]
        return {"report": {"candidates": cands}, "live": True}
    except Exception as e:
        print(f"[Scout] API error: {e} — using static fallback")
        rep = _static_scout(theme, owned)
        rep["note"] = f"Live search unavailable ({e}); showing curated seeds."
        return {"report": rep, "live": False}
