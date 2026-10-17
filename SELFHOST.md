# DramaClaw Selfhost

This repository packages DramaClaw with the pluggable Provider Hub. Provider
Hub keeps upstream credentials, model bindings, protocol adapters, and remote
ComfyUI workflows outside DramaClaw's core application.

No provider credentials are included in this repository. Add them through the
Provider Hub management UI after deployment.

## Ports

The examples use host ports above 10000:

| Service | URL |
| --- | --- |
| DramaClaw Web | `http://localhost:19080` |
| DramaClaw API | `http://localhost:19780` |
| Provider Hub UI and gateway | `http://localhost:18001` |

Container-internal ports remain unchanged. Start DramaClaw with explicit host
ports after creating your local `.env` from `.env.example`:

```bash
ST_WEB_PORT=19080 ST_API_PORT=19780 docker compose up -d --build
```

## 1. Start Provider Hub

```bash
cd provider-hub
docker compose up -d --build
```

Open `http://localhost:18001` and add services for the capabilities you use,
such as text, vision, embedding, image, video, and TTS. Configure credentials
in the UI; do not place real keys in tracked files.

Provider resolution follows this order:

1. An exact incoming model override.
2. The capability binding.
3. The active default service for that capability.

This lets DramaClaw keep stable logical model names while Provider Hub selects
the upstream model.

## 2. Connect DramaClaw

In DramaClaw's model configuration, select the custom/self-hosted provider and
use this OpenAI-compatible gateway base URL when DramaClaw runs in Docker:

```text
http://host.docker.internal:18001/v1
```

For a host-native DramaClaw process, use:

```text
http://127.0.0.1:18001/v1
```

If Provider Hub authentication is enabled, enter the matching gateway token in
DramaClaw. The default local compose binding only exposes Provider Hub on
`127.0.0.1`; configure authentication and TLS before exposing it to a network.

## 3. Remote ComfyUI

Provider Hub can call a local or remote ComfyUI instance without NewAPI:

1. Add a `video` service in Provider Hub.
2. Select the `comfyui_native` protocol.
3. Enter the ComfyUI server root, such as
   `http://host.docker.internal:18188` or a reachable HTTPS address.
4. Add the model name and an API-format ComfyUI workflow.
5. Bind the service to the `video` capability.

The ComfyUI address is the server root whose API exposes `/prompt`, `/history`,
`/view`, and upload endpoints. It is often the same host and port used by the
ComfyUI web interface, but it must be reachable from the Provider Hub container.

## Local state

Provider Hub persists configuration in its Docker volume. DramaClaw persists
its application settings and generated data separately. Back up both volumes,
and keep credentials in local configuration or a secret manager. Files such as
`.env`, SQLite databases, logs, generated output, and browser artifacts are
ignored and must not be committed.

Upstream retired `docker-compose.selfhosted.yml`; use the maintained
`docker-compose.yml` or `docker-compose.release.yml`. Provider Hub runs separately.
The source compose file also expects the upstream `dramaclaw-gateway` sibling
checkout; see README for the current source-build setup.

The sample `.env.example` explicitly selects Provider Hub for character, sketch,
render, prop and scene images. Without those overrides, upstream official image
defaults remain unchanged. Configure text/vision via the custom gateway settings;
official mode retains upstream BrainClaw defaults.
