### Phase 2.2 — Page Search

Implemented title search with shaped output containing page IDs,
titles, URLs, and pagination metadata. The client reuses the
authenticated request layer and preserves actionable errors.

Validation:

- Live search returned accessible pages.
- A deliberately unlikely query returned an empty result.
- Cursor pagination returned subsequent results.
- All six OAuth, request-layer, and search tests passed.

Observed limitation:
Some live search results did not contain the literal query text
in their titles. These results were already present in the raw
API response. The server-side matching cause remains unconfirmed.
The client preserves API results; callers should inspect titles
before selecting a page ID.
