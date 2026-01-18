import json
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st

DATA_DIR = "data"
WORDLIST_PATH = os.path.join(DATA_DIR, "wordlists.json")


# -----------------------------
# Persistence helpers
# -----------------------------
def ensure_data_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WORDLIST_PATH):
        default = {
            "tiers": ["Common", "Rare", "Epic"],
            "adjectives": {"Common": [], "Rare": [], "Epic": []},
            "nouns": {"Common": [], "Rare": [], "Epic": []},
        }
        save_wordlists(default)


def load_wordlists() -> Dict:
    ensure_data_file()
    with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_wordlists(data: Dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(WORDLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_words(text: str) -> List[str]:
    raw = re.split(r"[\n,]+", text)
    words: List[str] = []
    for w in raw:
        w = w.strip()
        if not w:
            continue
        w = re.sub(r"[^A-Za-z \-']", "", w).strip()
        if w:
            words.append(w)

    # dedupe while keeping order
    seen = set()
    out = []
    for w in words:
        key = w.lower()
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


# -----------------------------
# Generator logic
# -----------------------------
def apply_case(s: str, mode: str) -> str:
    if mode == "Title Case":
        return s.title()
    if mode == "UPPER":
        return s.upper()
    if mode == "lower":
        return s.lower()
    return s


def join_name(adj: str, noun: str, separator: str) -> str:
    if separator == "Space":
        return f"{adj} {noun}"
    if separator == "Hyphen":
        return f"{adj}-{noun}"
    if separator == "Underscore":
        return f"{adj}_{noun}"
    if separator == "of":
        return f"{adj} of {noun}"
    return f"{adj} {noun}"


def pick_word_from_tiers(
    lists: Dict[str, List[str]],
    tier_weights: Dict[str, int],
    rng: random.Random,
) -> Optional[Tuple[str, str]]:
    """Returns (tier, word) or None."""
    available_tiers = [t for t, w in tier_weights.items() if w > 0 and len(lists.get(t, [])) > 0]
    if not available_tiers:
        return None
    weights = [tier_weights[t] for t in available_tiers]
    tier = rng.choices(available_tiers, weights=weights, k=1)[0]
    return tier, rng.choice(lists[tier])


def generate_one_name(
    adjectives: Dict[str, List[str]],
    nouns: Dict[str, List[str]],
    tier_weights: Dict[str, int],
    separator: str,
    case_mode: str,
    alliteration: bool,
    avoid_duplicates: bool,
    used_names: set,
    rng: random.Random,
) -> Optional[Tuple[str, str, str]]:
    """
    Returns (final_name, adj_tier, noun_tier) or None.
    """

    # Precompute enabled noun pool by letter for alliteration
    enabled_nouns: List[Tuple[str, str]] = []  # (tier, noun)
    for t, w in tier_weights.items():
        if w > 0:
            for n in nouns.get(t, []):
                enabled_nouns.append((t, n))

    nouns_by_letter: Dict[str, List[Tuple[str, str]]] = {}
    for t, n in enabled_nouns:
        if n:
            nouns_by_letter.setdefault(n[0].lower(), []).append((t, n))

    tries = 0
    while tries < 250:
        tries += 1

        picked_adj = pick_word_from_tiers(adjectives, tier_weights, rng)
        if not picked_adj:
            return None
        adj_tier, adj_raw = picked_adj

        if alliteration:
            letter = adj_raw[0].lower()
            candidates = nouns_by_letter.get(letter, [])
            if not candidates:
                continue
            noun_tier, noun_raw = rng.choice(candidates)
        else:
            picked_noun = pick_word_from_tiers(nouns, tier_weights, rng)
            if not picked_noun:
                return None
            noun_tier, noun_raw = picked_noun

        adj = apply_case(adj_raw, case_mode)
        noun = apply_case(noun_raw, case_mode)
        final_name = join_name(adj, noun, separator)

        if avoid_duplicates and final_name.lower() in used_names:
            continue

        return final_name, adj_tier, noun_tier

    return None


def split_for_display(final_name: str) -> Tuple[str, str]:
    if " of " in final_name:
        a, b = final_name.split(" of ", 1)
        return a, b
    if "-" in final_name:
        a, b = final_name.split("-", 1)
        return a, b
    if "_" in final_name:
        a, b = final_name.split("_", 1)
        return a, b
    parts = final_name.split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


# -----------------------------
# UI / CSS
# -----------------------------
def inject_css():
    st.markdown(
        """
        <style>
          :root{
            --pw-primary:  #2EC8FF;
            --pw-primary2: #35E7C7;
            --pw-border:   rgba(255,255,255,0.14);
            --pw-card:     rgba(255,255,255,0.06);
            --pw-glow:     rgba(46,200,255,0.35);
            --pw-glow2:    rgba(53,231,199,0.30);
          }

          /* ----------------------------------
             GLOBAL LAYERING FIX (CRITICAL)
             ---------------------------------- */

          /* Background particles (very bottom) */
          .pw-particles{
            position: fixed;
            inset: 0;
            overflow: hidden;
            pointer-events: none;
            z-index: 0;
          }

          /* Entire Streamlit app ABOVE particles */
          div[data-testid="stAppViewContainer"]{
            position: relative;
            z-index: 1;
          }

          /* Sidebar, header, footer always on top */
          header, footer, section[data-testid="stSidebar"]{
            position: relative;
            z-index: 2;
          }

          /* ----------------------------------
             BACKGROUND VIBE
             ---------------------------------- */
          body{
            background:
              radial-gradient(900px 520px at 10% 6%, rgba(46,200,255,0.12), transparent 60%),
              radial-gradient(900px 520px at 90% 18%, rgba(53,231,199,0.10), transparent 60%),
              radial-gradient(700px 520px at 50% 115%, rgba(7,27,39,0.55), transparent 65%);
          }

          /* ----------------------------------
             SLOT UI
             ---------------------------------- */
          .slot-wrap{
            border: 1px solid var(--pw-border);
            background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
          }

          .slot-machine{
            display:flex;
            gap: 12px;
          }

          .reel{
            flex:1;
            height:110px;
            display:flex;
            align-items:center;
            justify-content:center;
            border-radius:16px;
            border:1px solid var(--pw-border);
            background:var(--pw-card);
            position:relative;
            overflow:hidden;
          }

          .reel::before{
            content:"";
            position:absolute;
            inset:0;
            background: repeating-linear-gradient(
              to bottom,
              rgba(255,255,255,0.05),
              rgba(255,255,255,0.05) 2px,
              transparent 6px,
              transparent 10px
            );
            opacity:0.25;
          }

          .reel::after{
            content:"";
            position:absolute;
            left:-40%;
            top:0;
            width:60%;
            height:100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
            transform: skewX(-18deg);
            animation: sweep 2.4s ease-in-out infinite;
          }

          @keyframes sweep{
            0%{ transform: translateX(-120%) skewX(-18deg); opacity:0; }
            40%{ opacity:.7; }
            100%{ transform: translateX(260%) skewX(-18deg); opacity:0; }
          }

          .reel-text{
            font-size:2rem;
            font-weight:800;
            text-shadow:0 6px 18px rgba(0,0,0,.35);
          }

          .reveal{
            box-shadow:0 0 40px var(--pw-glow);
          }
          .reveal-epic{
            box-shadow:0 0 46px var(--pw-glow2);
          }

          /* ----------------------------------
             PRIMARY BUTTON (PALWORLD BLUE)
             ---------------------------------- */
          div.stButton > button[kind="primary"]{
            background: linear-gradient(90deg, var(--pw-primary), var(--pw-primary2)) !important;
            color:#05202D !important;
            font-weight:900 !important;
            border-radius:14px !important;
            border:1px solid rgba(255,255,255,.22) !important;
            box-shadow:0 12px 30px rgba(46,200,255,.18) !important;
          }
        </style>

        <!-- BACKGROUND PARTICLES -->
        <div class="pw-particles" aria-hidden="true">
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
        </div>

        <style>
          .pw-particle{
            position:absolute;
            width:8px;
            height:8px;
            border-radius:50%;
            background: radial-gradient(circle, rgba(255,255,255,.5), rgba(46,200,255,.2), transparent);
            animation: floatUp linear infinite;
            opacity:.35;
          }

          @keyframes floatUp{
            0%   { transform: translateY(0);   opacity:0; }
            10%  { opacity:.35; }
            100% { transform: translateY(-120vh); opacity:0; }
          }

          .pw-particle:nth-child(1)  { left:5%;  bottom:-10%; animation-duration:18s; }
          .pw-particle:nth-child(2)  { left:15%; bottom:-15%; animation-duration:22s; }
          .pw-particle:nth-child(3)  { left:25%; bottom:-12%; animation-duration:20s; }
          .pw-particle:nth-child(4)  { left:35%; bottom:-18%; animation-duration:24s; }
          .pw-particle:nth-child(5)  { left:45%; bottom:-14%; animation-duration:19s; }
          .pw-particle:nth-child(6)  { left:55%; bottom:-20%; animation-duration:26s; }
          .pw-particle:nth-child(7)  { left:65%; bottom:-16%; animation-duration:21s; }
          .pw-particle:nth-child(8)  { left:75%; bottom:-13%; animation-duration:23s; }
          .pw-particle:nth-child(9)  { left:85%; bottom:-19%; animation-duration:25s; }
          .pw-particle:nth-child(10) { left:95%; bottom:-11%; animation-duration:27s; }
        </style>
        """,
        unsafe_allow_html=True
    )


    # Particles markup (separately, avoids broken HTML inside style blocks)
    st.markdown(
        """
        <div class="pw-particles" aria-hidden="true">
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
          <span class="pw-particle"></span><span class="pw-particle"></span><span class="pw-particle"></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def slot_card_html(adj: str, noun: str, label_left: str, label_right: str, reveal: bool, epic: bool) -> str:
    cls = "reel reveal-epic" if (reveal and epic) else ("reel reveal" if reveal else "reel")
    return f"""
    <div class="slot-wrap">
      <div class="slot-topline">
        <span class="tiny-pill">{label_left}</span>
        <span class="subtle">Pal Name Pull</span>
        <span class="tiny-pill">{label_right}</span>
      </div>

      <div class="slot-machine">
        <div class="{cls}">
          <div class="reel-text">{adj}</div>
        </div>
        <div class="divider"></div>
        <div class="{cls}">
          <div class="reel-text">{noun}</div>
        </div>
      </div>
    </div>
    """


def do_slot_animation(
    adjectives: Dict[str, List[str]],
    nouns: Dict[str, List[str]],
    tiers: List[str],
    tier_weights: Dict[str, int],
    separator: str,
    case_mode: str,
    alliteration: bool,
    avoid_duplicates: bool,
    used_names: set,
) -> Optional[Tuple[str, str]]:
    rng = random.Random()

    enabled_adjs = []
    enabled_nouns = []
    for t in tiers:
        if tier_weights.get(t, 0) > 0:
            enabled_adjs.extend(adjectives.get(t, []))
            enabled_nouns.extend(nouns.get(t, []))

    if not enabled_adjs or not enabled_nouns:
        return None

    slot_area = st.empty()
    msg_area = st.empty()

    # Spin pacing
    schedule = [0.03] * 18 + [0.05] * 14 + [0.08] * 10 + [0.12] * 6

    for i, dt in enumerate(schedule):
        adj = apply_case(rng.choice(enabled_adjs), case_mode)
        noun = apply_case(rng.choice(enabled_nouns), case_mode)

        slot_area.markdown(slot_card_html(adj, noun, "Spinning…", "Spinning…", reveal=False, epic=False), unsafe_allow_html=True)

        if i in (8, 22, 34):
            msg_area.info(
                rng.choice(
                    [
                        "Calibrating vibes…",
                        "Consulting the Pal Council…",
                        "Charging the naming crystals…",
                        "Rolling destiny…",
                    ]
                )
            )
        time.sleep(dt)

    picked = generate_one_name(
        adjectives=adjectives,
        nouns=nouns,
        tier_weights=tier_weights,
        separator=separator,
        case_mode=case_mode,
        alliteration=alliteration,
        avoid_duplicates=avoid_duplicates,
        used_names=used_names,
        rng=rng,
    )
    if not picked:
        return None

    final_name, adj_tier, noun_tier = picked
    a, b = split_for_display(final_name)

    # Epic: stronger glow only (no particles)
    final_tier = adj_tier if adj_tier else noun_tier
    is_epic = str(final_tier).lower() == "epic"

    msg_area.empty()
    slot_area.markdown(
        slot_card_html(a, b, f"REVEAL • {final_tier}", "✨ Locked In", reveal=True, epic=is_epic),
        unsafe_allow_html=True,
    )

    return final_name, final_tier


# -----------------------------
# Streamlit App
# -----------------------------
st.set_page_config(page_title="Palworld Pal Name Slot", page_icon="🐾", layout="wide")
inject_css()

st.title("🐾 Palworld Pal Name Generator — Slot Pull Edition")
st.caption("One pull. Two parts. Maximum drama. **Adjective + Noun**.")

data = load_wordlists()
tiers = data.get("tiers", ["Common", "Rare", "Epic"])
adjectives = data.get("adjectives", {})
nouns = data.get("nouns", {})

# session state
if "last_name" not in st.session_state:
    st.session_state["last_name"] = None
if "used_names" not in st.session_state:
    st.session_state["used_names"] = set()
if "history" not in st.session_state:
    st.session_state["history"] = []  # list[(time, name, tier)]


with st.sidebar:
    st.header("Generator Settings")
    separator = st.selectbox("Separator", ["Space", "Hyphen", "Underscore", "of"], index=0)
    case_mode = st.selectbox("Case", ["Title Case", "UPPER", "lower"], index=0)

    alliteration = st.checkbox("Alliteration (same starting letter)", value=False)
    avoid_duplicates = st.checkbox("Avoid duplicates (session)", value=True)

    st.divider()
    st.subheader("Rarity / Tier Mix")
    st.caption("Weights control tier probability. Set 0 to disable a tier.")

    tier_weights = {}
    for t in tiers:
        default = 5 if t == "Common" else (3 if t == "Rare" else 1)
        tier_weights[t] = st.slider(f"{t} weight", 0, 10, default)

    st.divider()
    if st.button("🧹 Clear session duplicates"):
        st.session_state["used_names"] = set()
        st.success("Cleared session duplicate memory.")


left, right = st.columns([1.3, 1])

with left:
    st.subheader("🎰 Pull a Pal Name")
    pull = st.button("PULL THE LEVER KRONK! ✨", type="primary", use_container_width=True)

    slot_idle = st.empty()

    if not st.session_state["last_name"] and not pull:
        slot_idle.markdown(slot_card_html("Ready", "To Pull", "Idle", "Idle", reveal=False, epic=False), unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.info("Hit the button to roll a single special name.")

    if pull:
        result = do_slot_animation(
            adjectives=adjectives,
            nouns=nouns,
            tiers=tiers,
            tier_weights=tier_weights,
            separator=separator,
            case_mode=case_mode,
            alliteration=alliteration,
            avoid_duplicates=avoid_duplicates,
            used_names=st.session_state["used_names"],
        )

        if not result:
            st.error("No valid name could be generated. Check if enabled tiers have words.")
        else:
            final, tier = result
            st.session_state["last_name"] = final
            if avoid_duplicates:
                st.session_state["used_names"].add(final.lower())

            st.session_state["history"].insert(0, (datetime.now().strftime("%H:%M:%S"), final, tier))
            st.session_state["history"] = st.session_state["history"][:12]

    if st.session_state["last_name"]:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.text_area("Copy your latest pull", value=st.session_state["last_name"], height=70)


with right:
    st.subheader("📜 Recent Pulls")
    if st.session_state["history"]:
        lines = [f"{t} — {name}  [{tier}]" for (t, name, tier) in st.session_state["history"]]
        st.text_area("History", value="\n".join(lines), height=220)
    else:
        st.caption("No pulls yet.")

    st.divider()

    with st.expander("🛠️ Wordlist Editor (click to expand)", expanded=False):
        st.caption("Edits are persistent and saved to data/wordlists.json")
        tab1, tab2, tab3 = st.tabs(["Edit Lists", "Import/Export", "Advanced"])

        with tab1:
            edit_tier = st.selectbox("Tier", tiers, index=0)
            st.markdown("### Adjectives")
            adj_text = st.text_area(
                "One per line (or comma-separated)",
                value="\n".join(adjectives.get(edit_tier, [])),
                height=160,
                key=f"adj_{edit_tier}",
            )

            st.markdown("### Nouns")
            noun_text = st.text_area(
                "One per line (or comma-separated)",
                value="\n".join(nouns.get(edit_tier, [])),
                height=160,
                key=f"noun_{edit_tier}",
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Save tier lists", use_container_width=True):
                    adjectives[edit_tier] = normalize_words(adj_text)
                    nouns[edit_tier] = normalize_words(noun_text)
                    data["adjectives"] = adjectives
                    data["nouns"] = nouns
                    save_wordlists(data)
                    st.success("Saved to data/wordlists.json")

            with c2:
                if st.button("↩️ Reload from disk", use_container_width=True):
                    st.rerun()

        with tab2:
            st.markdown("### Export")
            export_json = json.dumps(data, indent=2, ensure_ascii=False)
            st.download_button(
                "⬇️ Download wordlists.json",
                data=export_json,
                file_name="wordlists.json",
                mime="application/json",
                use_container_width=True,
            )

            st.markdown("### Import")
            uploaded = st.file_uploader("Upload a wordlists.json", type=["json"])
            if uploaded is not None:
                try:
                    new_data = json.load(uploaded)
                    if "adjectives" in new_data and "nouns" in new_data and "tiers" in new_data:
                        save_wordlists(new_data)
                        st.success("Imported and saved. Reloading…")
                        st.rerun()
                    else:
                        st.error("JSON missing required keys: tiers, adjectives, nouns.")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")

        with tab3:
            st.markdown("### Add/Remove Tiers (optional)")
            st.caption("Only touch if you want more tiers than Common/Rare/Epic.")

            new_tier = st.text_input("Add tier name", value="")
            if st.button("➕ Add tier", use_container_width=True):
                t = new_tier.strip()
                if t and t not in tiers:
                    tiers.append(t)
                    data["tiers"] = tiers
                    data["adjectives"].setdefault(t, [])
                    data["nouns"].setdefault(t, [])
                    save_wordlists(data)
                    st.success(f"Added tier: {t}")
                    st.rerun()
                else:
                    st.warning("Tier name empty or already exists.")

            remove_tier = st.selectbox("Remove tier", ["(select)"] + tiers)
            if st.button("🗑️ Remove selected tier", use_container_width=True):
                if remove_tier != "(select)":
                    if remove_tier in tiers:
                        tiers.remove(remove_tier)
                        data["tiers"] = tiers
                        data["adjectives"].pop(remove_tier, None)
                        data["nouns"].pop(remove_tier, None)
                        save_wordlists(data)
                        st.success(f"Removed tier: {remove_tier}")
                        st.rerun()
                else:
                    st.warning("Pick a tier to remove.")

