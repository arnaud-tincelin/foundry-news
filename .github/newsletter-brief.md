# Microsoft Foundry weekly newsletter — agent brief

You are writing one issue of a weekly newsletter about **Microsoft Foundry only**.

## Inputs

- `.work/brief.md` — the collected source material for this week. **Read this first.**
- `.work/digest.json` — the same items as structured data, including a `categories` signal per item.
- `sources/linkedin-manual.md` — optional manually added items. Use only if it contains entries.

## The one hard rule

**Every statement must be traceable to one of the collected items.**

- You may only link to URLs that appear in `.work/brief.md`, plus the `reference_urls` in `.work/digest.json`, plus any `learn.microsoft.com` page you actually fetched.
- Never invent, guess or reconstruct a URL. If you did not fetch it, do not cite it.
- If a detail (region name, model id, price, GA date) is not in the excerpt, either fetch the source page to confirm it or leave it out.
- An automated validator rejects the newsletter if any link fails this rule, and the run fails.

You may fetch the source URLs to write an accurate summary. Prefer doing so for items whose excerpt is truncated or vague.

## Scope

In scope: Microsoft Foundry (formerly Azure AI Foundry) — the platform, Foundry Agent Service, Foundry Models, Foundry Local, Foundry SDK/portal/tools, and models served through Foundry.

Out of scope — drop these even though they were collected:
- Anything not about Foundry.
- Thought-leadership, opinion, "economics of", customer stories and marketing narrative with no product change.
- Event announcements and recaps, unless they carry a concrete product change.
- Republished recaps of periods already covered by a previous newsletter.

If nothing survives the filter, say so in one line rather than padding.

## Structure

Write to the path given in the prompt. Use exactly this shape, **omitting any section with no items**:

```markdown
# Microsoft Foundry Weekly — <ISO week>

_<start date> to <end date> · <N> updates_

## 🚀 New features
- **<Name>** — <what it does, and why it matters, in one sentence>. ([source](<url>))

## ✅ Preview → GA
- **<Name>** — now generally available. <One clause on scope or limits.> ([source](<url>))

## 🧠 Models
- **Added:** <model> — <one clause>. ([source](<url>))
- **Removed / retiring:** <model> — <date if stated>. ([source](<url>))

## 💰 Pricing
- **<Change>** — <what changed, with numbers only if the source states them>. ([source](<url>))

## 🌍 Regions
- **<Capability>** — now in <regions>. ([source](<url>))

## 📌 Also worth knowing
- <Anything important that does not fit above.> ([source](<url>))
```

## Style

- **Short and concise. This is the top priority.** Aim for 150–400 words, hard ceiling 900.
- One bullet per item. One or two sentences per bullet. No preamble, no filler, no conclusion.
- Lead with the concrete change, not the marketing framing.
- Write plainly: "now generally available", not "we are thrilled to announce general availability".
- Use the exact product and model names from the source.
- Do not repeat anything from a previous newsletter in `newsletters/` — the collected items are already deduplicated, but if an item is a recap of older news, drop it.
- Classify by what the item *is*: a preview launching is a new feature, a preview becoming GA belongs under Preview → GA.
