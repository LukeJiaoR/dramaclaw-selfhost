# DramaClaw Provider Hub

Independent provider runtime for DramaClaw. It exposes stable OpenAI-compatible
endpoints while provider credentials, defaults, model overrides, and protocol
adapters remain outside the DramaClaw repository.

## Run

```bash
docker compose up -d --build
```

Management UI: `http://localhost:18001`

Gateway base URL: `http://host.docker.internal:18001/v1`

The host port is bound to `127.0.0.1` by default. Set `PROVIDER_HUB_API_KEY` in
`docker-compose.yml` when exposing the service beyond the local machine.

## Provider resolution

Requests resolve in this order:

1. Exact incoming model override.
2. Capability binding (`text`, `vision`, `image`, `video`, `tts`, and so on).
3. The active default service for that capability.

DramaClaw model aliases therefore do not need to be configured individually.

## Adapter plugins

External packages can register adapters through the
`dramaclaw_provider_hub.adapters` Python entry-point group. An adapter declares
one or more protocol names and implements the `ProviderAdapter` protocol from
`provider_hub.registry`.

Built-in protocols:

- `openai`, `openai_compatible`
- `openai_audio_speech`
- `mimo_chat_audio`
- `openai_video`, `volcengine_omni`, `xai`, `veo3`
- `comfyui_native`

Provider-specific video payload conversions can be added as separate plugins
without changing the gateway routes or configuration database.

## Native ComfyUI

Provider Hub can call a local or remote ComfyUI server directly. NewAPI is not
part of this route.

1. Add a `video` service in the management UI.
2. Select `comfyui_native` as its protocol.
3. Set Base URL to the ComfyUI server root, for example
   `http://host.docker.internal:8188` or a reachable remote HTTPS URL.
4. Declare the DramaClaw model name in Models.
5. Add one or more API Format workflows. Models declared by a native ComfyUI
   service automatically receive exact video routes.

Workflow modes may include `text_to_video`, `first_frame`,
`first_last_frame`, `image_reference`, `all_reference`, and `video_edit`.
Provider Hub downloads DramaClaw relay assets, uploads them to ComfyUI, injects
prompt/duration/geometry/seed and media inputs, submits `/prompt`, polls
`/history/{prompt_id}`, and proxies the `/view` output back to DramaClaw.

Semantic node matching follows the same conventions used by LocalMiniDrama:
`LoadImage`, `LoadAudio`, `LoadVideo`, `CR Text`, titled duration/width/height
inputs, `RandomNoise`, and `VHS_VideoCombine`. For other workflows, use the
optional node bindings JSON on each workflow, for example:

```json
{
  "prompt": {"node": "6", "input": "text"},
  "duration": {"node": "12", "input": "value"},
  "images": [
    {"node": "20", "input": "image"},
    {"node": "21", "input": "image"}
  ]
}
```

When ComfyUI is behind an authenticated proxy, put the bearer token in API Key
or add custom headers in Additional Settings. Upload endpoints can also be
overridden there with `upload_endpoints`.
