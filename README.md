# ydns-py

**ydns-py** is a simple, standalone, unofficial YDNS dynamic DNS updater written in Python, with no dependencies on external libraries. Rather than using the [legacy v1 API](https://ydns.io/api/v1/), it relies on update URLs, which require no credentials and which YDNS provides for each of your DNS records.

While YDNS supports TXT and CAA records in addition to A and AAAA, and also allows for creating multiple A/AAAA records per domain (round-robin DNS), this script is limited to the dynamic DNS use case. It only supports assigning your current externally visible IPv4/IPv6 address to one A/AAAA record per domain.

The script has been tested under Linux and macOS, but should support any Unix-like OS with Python >= 3.11 installed. Windows support is not planned, but possibly you can make this work under WSL as-is?

This project is not in any way affiliated with or endorsed by YDNS or TFMT GmbH.
The copyright for the name YDNS belongs to TFMT GmbH, and the author does not claim any copyright for the name **ydns-py**.

## Installation

You should be able to do any of the following, depending on your needs, environment and installed tools:

```
# install into an isolated environment
uv tool install ydns-py
pipx install ydns-py

# install into your global Python environment or active virtualenv
uv pip install ydns-py
pip install ydns-py  

# direct runs without installation
uvx ydns-py
pipx run ydns-py
```

As for other tools than uv(x) or pip(x), you'll need to figure it out yourself.

## Configuration

You'll store your domains and their update URLs in a TOML file. By default, the script looks for `~/.config/ydns-py/config.toml` first, then only if it's not found, `/etc/ydns-py.toml`. You can specify a different path with `--config <file>`.

You can find the update URLs by logging into your YDNS account. Under the record list page for each domain, each record has a clickable icon with a "Get Update URL" tooltip.

Note that update URLs are sensitive information, so you should ensure your configuration file is not readable by outsiders.

Below, an example configuration file with two domains, the first one with update URLs for DNS records of both IPv4 (A) and IPv6 (AAAA) address families, the second one with IPv4 only:

```toml
[[domains]]
domain = "example.ydns.eu"
update_url = "https://ydns.io/hosts/update/Wh4tAL0velYDayforS0meDNS"
update_url_v6 = "https://ydns.io/hosts/update/Wh4tAL0velYDayforIPv6ing"

[[domains]]
domain = "example2.ydns.eu"
update_url = "https://ydns.io/hosts/update/AL0ngRand0mString1sHeree"
```

The `domain` entries are strictly informational and therefore optional, but they're obviously recommended for readability when dealing with multiple domains.

## Usage

You can just run the script manually, but you'll likely want it to execute periodically (e.g. cron, systemd timers), or in response to a detected external IP address change.

Please be considerate and don't flood YDNS with update requests. Periodic execution probably shouldn't happen more often than once every five minutes. Check [ydns.io](https://ydns.io) for any guidance they may have on this topic.

No output is printed for a successful request of an update URL, unless you specify `-v/--verbose`, in which case a single line is printed to `stdout` for each requested URL.

Each request to an update URL that produces a non-2xx status code will cause a message to be logged to `stderr`. Since the update URLs are independent of each other, the script will never abort just because individual update URLs return non-2xx.

By default, the script operates in "lax mode". In this mode, any non-2xx HTTP codes returned by any update URLs will not cause the script exit code to become non-zero. Non-zero codes are reserved for conveying configuration or connection errors.

Using `-s/--strict` activates "strict mode", where the script will exit with code 4 if any update URL returned a non-2xx code. All update URLs will still be processed, as indicated above.

## Errors and troubleshooting

To summarize, the exit codes in lax and strict mode in various situations are the following (configuration-related errors will have codes 1–3, but connections are not even attempted in that case):

```
┌──────────────────────────┬─────┬────────┐
│        Situation         │ Lax │ Strict │
├──────────────────────────┼─────┼────────┤
│ Any non-2xx HTTP code    │  0  │   4    │
├──────────────────────────┼─────┼────────┤
│ Any connection error     │  5  │   5    │
├──────────────────────────┼─────┼────────┤
│ Both HTTP and conn error │  5  │   5    │
└──────────────────────────┴─────┴────────┘
```

The script will attempt forced IPv4 and IPv6 requests with `update_url` and `update_url_v6`, respectively. If one type of request fails (IPv6, more likely), try calling the IP retrieval URL `https://ydns.io/api/v1/ip`, using `curl -6` or `curl -4` to force the address family. This will give you some idea of what might be wrong.

## Deployment examples

### systemd

In this example, with a system-level service without `User=`, and the script executed without a `--config` parameter, the configuration would be looked for in `/root/.config/ydns-py/config.toml` first, then `/etc/ydns-py.toml`.

`/etc/systemd/system/ydns.service`:

```
[Unit]
Description=YDNS dynamic DNS updater
Documentation=https://github.com/jklaiho/ydns-py
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Varies depending on your Python environment and choice of installer/runner
ExecStart=/path/to/ydns-py
NoNewPrivileges=yes
ProtectSystem=strict
```

`/etc/systemd/system/ydns.timer`:

```
[Unit]
Description=Run the YDNS updater periodically

[Timer]
# Run 2 minutes after boot to give the network time to come up.
OnBootSec=2min
# Then run every 5 minutes.
OnUnitActiveSec=5min
# If the system was off when a trigger was due, run it on next boot.
Persistent=true

[Install]
WantedBy=timers.target
```

After these are in place:

```
sudo systemctl daemon-reload
sudo systemctl enable --now ydns.timer
```

Executing the script as a user service rather than a system service is left as an exercise for the reader. Note that `network-online.target` is not available for user services, so you'd likely use `default.target` in `After=`/`Wants=`.

## Contributing

Pull requests are welcome. Be warned though, this project was born out of a personal need, fulfilled them with the first version, and is not expected to see very active development beyond fixing bugs or adapting to YDNS service changes.

Contributors should install [prek](https://prek.j178.dev) and then activate it for their cloned git repo using `prek install --install-hooks`. The hooks handle formatting and linting with [Ruff](https://astral.sh/ruff).

Install [uv](https://astral.sh/uv). Run `uv sync` to create `.venv`. This installs ydns-py in editable mode, so to test your changes just run `uv run ydns-py`.

## License

This project is in the public domain, as described by [The Unlicense](https://unlicense.org).
