# Manually added sources

LinkedIn blocks all automated access (it returns HTTP 999 to non-browser
clients, has no public feed, and scraping it breaks its terms of use), so
**Sunita Kannan's LinkedIn posts cannot be collected automatically.**

If you want an item from her feed — or any other official Microsoft
announcement the feeds missed — add it below before the Monday 06:00 UTC run
and the agent will pick it up.

## Rules

- Only add items that link to an **official Microsoft page**
  (`devblogs.microsoft.com`, `azure.microsoft.com`, `learn.microsoft.com`,
  `techcommunity.microsoft.com`, `blogs.microsoft.com`, `news.microsoft.com`).
  A LinkedIn post is a pointer, not a source — cite the Microsoft page it
  refers to. The validator rejects non-Microsoft links.
- Delete entries once they have been published in a newsletter.

## Format

```markdown
- **<Headline>** — <one sentence on what changed> — https://<official-microsoft-url>
```

## Pending items

<!-- Add entries here. Leave empty when there are none. -->
