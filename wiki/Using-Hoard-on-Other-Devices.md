Hoard only serves the computer it runs on, unless you ask it to share. Shared, your phone, tablet or another
computer can browse your library and downloads. Signing in, refreshing, downloading, signing out, changing tags
or settings and opening folders still only work on the computer running Hoard.

## What it needs

Your library and Hoard's access key would cross your network, so sharing needs one of:

- **HTTPS**, with a certificate for the computer running Hoard. The free tool [mkcert](https://github.com/FiloSottile/mkcert)
  makes one your devices will trust.
- **An encrypted network** your devices already use to reach that computer, such as
  [Tailscale](https://tailscale.com/) or WireGuard.

## Starting Hoard for other devices

With HTTPS:

```
hoard-cli --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
```

Over Tailscale or another encrypted network:

```
hoard-cli --host 0.0.0.0 --plain-http
```

(From source, `Hoard.bat` or `./run.sh` in place of `hoard-cli`; see [Command line](Command-Line).) Add
`--port 8765` (or any free port) to keep the same port every time, and `--no-open` to not open a page on this
computer too. Windows may ask whether to let Hoard through the firewall: allow it on private networks.

Hoard then prints two addresses:

- **Other devices on your network:** `https://<this computer's address>:<port>/#key=...` (`http://` with
  `--plain-http`). Put the computer's name or network address in place of `<this computer's address>`, and open
  that on the other device.
- **Open Hoard at** the same address on `127.0.0.1`, for this computer.

## The access key

Every request for your library, downloads, pictures or an action needs the key in that address, even from the
computer running Hoard. It's new every time Hoard starts, so after a restart, open the new address. A device
keeps the key for that address until then, so bookmarking the page without the key works for the rest of that
run.

The key stops anyone who doesn't have it, but it isn't encryption: that's why HTTPS or an encrypted network is
required. Share the address only with devices you trust.

## Making a certificate with mkcert

1. Install [mkcert](https://github.com/FiloSottile/mkcert) on the computer running Hoard, and run
   `mkcert -install`.
2. Make a certificate for the names your devices will use, for example:
   `mkcert my-pc my-pc.local 192.168.1.20`. It writes a certificate and a key file.
3. Start Hoard with `--tls-cert` and `--tls-key` pointing at those two files.
4. On each other device, install and trust mkcert's root certificate (`mkcert -CAROOT` shows where it is), so it
   trusts the certificate.

The command-line reference covers these options too:
[docs/COMMAND-LINE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/COMMAND-LINE.md#using-hoard-from-other-devices).
