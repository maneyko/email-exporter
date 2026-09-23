# maneyko.email_exporter

The role that deploys this repo onto a host: uv, a system user, a clone at
`/opt/email-exporter`, per-account secrets in `/etc/email-exporter/secrets/`,
AWS credentials for the service user or a local root, and the systemd timer that
runs the export.

`requirements.yml`:

```yaml
collections:
  - name: https://github.com/maneyko/ansible-roles.git
    type: git
    version: main
  - name: https://github.com/maneyko/email-exporter.git#/ansible
    type: git
    version: main
```

The `#/ansible` fragment is the subdirectory the collection lives in — this repo
is an application that happens to ship its own deploy role, not a collection
repo.

`maneyko.roles` is listed because this role installs `uv` through
`maneyko.roles.uv`. It is not declared as a collection dependency in
`galaxy.yml`: that would send `ansible-galaxy` to the public Galaxy server
looking for a collection that is only published as a git repo.

```yaml
- hosts: all
  roles:
    - role: maneyko.email_exporter.deploy
      vars:
        config:  "{{ app_config }}"
        secrets: "{{ app_secrets }}"
```

`config` and `secrets` are deliberately generic: the caller holds one structure
per app and hands it over whole. Both are declared in
`roles/deploy/meta/argument_specs.yaml` and validated before the role runs:

    ansible-doc -t role maneyko.email_exporter.deploy   # collection installed
    ansible-doc -t role -r roles deploy                  # from this repo

Do not reach for `-M`: it is `--module-path`, and `ansible-doc -t role -M roles
<name>` prints nothing and **exits 0**, which is how a wrong invocation can sit
in a README for months.

`secrets.users` is a list of complete account TOML documents, exactly as the
exporter wants them on disk. Each is written to
`/etc/email-exporter/secrets/<username>.toml`, where `<username>` is read back
out of the TOML itself — so the list needs no keys and no parallel structure to
keep in sync.

`config.bucket_name` reaches the app as `BUCKET_NAME` in
`/etc/email-exporter/environment`, which the service unit loads. It goes
through a file rather than an `Environment=` line because the units are copied
out of the checkout verbatim, so there is nothing to interpolate a value into.

`config.root` is the alternative to `config.bucket_name`, and the role accepts
exactly one of them. It reaches the app as `STORAGE_ROOT` through the same
file. With it, the role installs no AWS credentials and writes a drop-in,
`email-exporter.service.d/storage.conf`, holding `RequiresMountsFor=<root>`:
the service pulls in whatever mount holds the root and fails if that mount
does. The root itself must already exist; the app refuses to create it.

`config.groups` adds the service user to existing groups, for a root whose
filesystem grants write access by group — a CIFS mount, where ownership is fixed
by mount options, is the case it exists for.

`config.timer: false` installs the timer but leaves it disabled and stopped, for
a host where something else runs `systemctl start email-exporter.service`. The
default is `true`.

`email_exporter_repo` in `roles/deploy/vars/main.yaml` is an HTTPS URL, so the
clone is anonymous and the play needs nothing on the SSH side. Override it with
an SSH URL to deploy from a private fork, and that brings back agent forwarding
(`ansible_ssh_extra_args: "-A"`) and `SSH_AUTH_SOCK` kept across `sudo`.

## What it lays down

| Path | Owner | Holds |
|---|---|---|
| `/opt/email-exporter` | `config.owner`, `2750` | the checkout; read-only to the service |
| `/etc/email-exporter/secrets/` | `config.owner:email-exporter`, `0750` | one `<address>.toml` per account, `0640` |
| `/etc/email-exporter/environment` | `config.owner`, `0644` | `BUCKET_NAME` or `STORAGE_ROOT`, loaded by the unit |
| `~email-exporter/.aws/` | the service user, `0700` | region and the access key pair; bucket only |
| `/etc/systemd/system/` | root | `email-exporter.service` and its `.timer` |
| `/etc/systemd/system/email-exporter.service.d/` | root | `storage.conf`, `RequiresMountsFor=`; local root only |

Defaults live in `roles/deploy/vars/main.yaml` rather than `defaults/`, because
they are facts about this app rather than knobs for a caller: the paths, the
service user, and the regex that reads a username back out of an account TOML.

**The units are copied, not linked.** `systemctl disable` deletes a unit file
that is a symlink into a checkout, so linking them would mean turning the timer
off also removed it.

`OnCalendar=daily`, deliberately: a first export of a large Gmail account is
throttled to roughly 2.5 GB/day, so the backfill is meant to take many runs and
each one is capped by `max_download_mib`.

## Gaps

- **The bucket's region is assumed, not passed.** `config.bucket_name` is a
  caller setting, but `email_exporter_aws_region` is still a role var, so a
  bucket outside `us-east-2` has to override it as a role param. A
  `config.aws_region` next to `config.bucket_name` would be the fix.
