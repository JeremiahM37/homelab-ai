# Declarative service plugin (`generic_http`)

You don't have to write Python to add a new service. For anything that speaks HTTP-JSON with a normal auth scheme, drop a config block and you're done.

## The 30-second example

```yaml
services:
  my_thing:
    plugin: generic_http        # tells homelab-ai to use the declarative plugin
    url: http://my-thing:8080
    auth:
      type: bearer
      key: ${MY_THING_TOKEN}
    health:
      path: /healthz
    tools:
      - name: list_widgets
        description: List widgets from My Thing.
        path: /api/widgets
        params:
          limit: {type: integer, default: 10}
      - name: get_widget
        description: Get one widget by ID.
        path: /api/widgets/{id}
        params:
          id: {type: string, required: true, in: path}
```

Restart. The agent now monitors `my_thing.health` every scan, and the AI agent has `list_widgets` and `get_widget` tools available.

## Auth types

| `auth.type` | What it does | Required keys |
|-------------|--------------|---------------|
| `none` (default) | No auth | — |
| `bearer` | `Authorization: Bearer <key>` | `key` |
| `header` | Any custom header | `header_name`, `value` (or `key`) |
| `basic` | HTTP Basic auth | `username`, `password` |
| `query` | API key in query string | `query_name`, `value` (or `key`) |

```yaml
auth:
  type: header
  header_name: X-Api-Key
  value: ${MY_KEY}
```

## Tool definition

Each entry under `tools:` becomes one AI-callable / MCP tool.

```yaml
- name: tool_name              # required — what the AI sees
  description: One-line desc   # required — used by the semantic router
  path: /api/resource/{id}     # required — `{key}` placeholders allowed
  method: GET                  # default GET
  params:
    id:
      type: string             # string | integer | number | boolean
      required: true
      in: path                 # path | query | body | header (default: query for GET, body for POST)
      default: ...             # optional; makes the param non-required
  body_template:               # optional — overrides automatic body building
    name: "{user_name}"
    tags: ["auto", "{kind}"]
  response:
    extract: data.items.0.name # optional — dot-path into the JSON response
```

### Param routing

| `in` value | Where it goes |
|-----------|---------------|
| `path` | Substituted into `{key}` in the URL (URL-encoded) |
| `query` | Appended as `?key=value` |
| `body` | Included in the JSON request body |
| `header` | Sent as a request header |

If you don't set `in`, GET defaults to `query` and POST/PUT/PATCH default to `body`.

### Response shaping

By default the tool returns the full JSON response. Setting `response.extract: foo.bar.0.name` walks a dot path through the JSON and returns just that value. Useful when the LLM only needs one field.

## Health check

```yaml
health:
  path: /healthz                # required
  method: GET                   # default
  ok_if:
    status_lt: 400               # default: 2xx and 3xx are healthy
    status: 200                  # OR require exactly this status
    body_contains: "ok"         # AND require this substring in the body
```

If you omit `ok_if` entirely, healthy = HTTP `< 400`.

## When to write Python instead

The declarative plugin covers single-request REST APIs. Stay with — or write — a Python plugin when you need:

- **Multi-step flows** (login → cookie → call, like qBittorrent).
- **Wire protocols other than HTTP** (NUT's TCP protocol).
- **Complex response transforms** beyond a dot-path extract.
- **Retry / circuit-breaker / rate-limit logic** specific to that service.

Existing built-in plugins (sonarr, jellyfin, qbittorrent, nut, …) keep using their hand-written code because they need this kind of flexibility. They aren't going anywhere; the declarative plugin is just the easier path for adding a new service.

## A real example: Linkwarden

```yaml
services:
  linkwarden:
    plugin: generic_http
    url: http://linkwarden:3050
    auth:
      type: bearer
      key: ${LINKWARDEN_TOKEN}
    health:
      path: /api/v1/tags
      ok_if: {status_lt: 401}
    tools:
      - name: linkwarden_search
        description: Search bookmarks by query string.
        path: /api/v1/links
        params:
          searchQueryString: {type: string, required: true}
          searchByName:      {type: boolean, default: true}
        response:
          extract: response
      - name: linkwarden_add_link
        description: Add a new bookmark.
        path: /api/v1/links
        method: POST
        params:
          name:        {type: string, required: true, in: body}
          url:         {type: string, required: true, in: body}
          description: {type: string,                 in: body}
```

That's a complete service integration — health-monitored, AI-callable, MCP-exposed — in 20 lines of YAML.
