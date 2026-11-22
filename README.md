# NonXig

NixOS configuration (flake + flake-parts, one file per aspect under `modules/`), host `nixos-btw`.

## What's in it
- **Desktop:** Mango (wlroots) compositor with Dux Shell and dux-greeter.
- **Kernel:** own optimized kernel and NVIDIA driver ([optimized-kernel](https://github.com/zenmastercat/optimized-kernel)).
- **Security:** [Nix-Protect-Barrior](https://github.com/zenmastercat/Nix-Protect-Barrior): build gate, Nix daemon hardening, local-only ports, store repair and daily audit (`modules/system/protect-barrior.nix`).
- **Yggdrasil:** encrypted mesh network (`modules/services/yggdrasil.nix`). Three public peers in Singapore and Hong Kong, private key kept in `/var/lib/yggdrasil` (never in the config), no LAN auto-peering, and every new incoming connection on `ygg0` dropped. To host something over Yggdrasil, add its port to `yggdrasilAllowedTCPPorts`.
- **Bongo Cat key feed:** lets the Dux Shell Bongo Cat plugin react to typing without putting the user in the `input` group; letters, digits and symbols are all sent as one key (`modules/desktop/bongo-keyfeed.nix`).
- Apps, Zsh, Foot, ROS overlay, Ollama/Docker services, VirtualBox, auto-updates.

## Use
```sh
doas nixos-rebuild switch --flake .#nixos-btw
```
With Nix-Protect-Barrior active, use `rebuild` (gate first) instead.

`security.acme.defaults.email` is a placeholder in this copy; set your own.
