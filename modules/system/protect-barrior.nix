{ inputs, ... }:
{
  # Nix-Protect-Barrior (github:zenmastercat/Nix-Protect-Barrior): build gate,
  # Nix daemon hardening, network barrier, store repair and daily audit.
  # Short commands (any shell):
  #   rebuild           doas npb-rebuild switch  (gate, then nixos-rebuild switch of /etc/nixos#nixos-btw)
  #   rebuild-boot      the same, active after the next boot
  #   barrier-approve   accept deliberate changes (new input, cache, ...); asks you to type APPROVE
  #   barrier-status    latest audit and store check
  #   barrier-audit     run the audit now, then show the status
  #   barrier-verify    check (and repair) the store now, then show the status
  flake.modules.nixos.protect-barrior = { ... }: {
    imports = [ inputs.nix-protect-barrior.nixosModules.default ];

    # Patched Nix: 2.34.8 (this nixpkgs' default) has CVE-2026-110450 (any daemon
    # user can get root). 2.34.9 is the same series with the fix.
    nix.package = inputs.nixpkgs-unstable.legacyPackages.x86_64-linux.nixVersions.nix_2_34;

    security.nixProtectBarrior = {
      enable = true;

      # Only root is a trusted Nix user (was: root, @wheel, lucas in ros/overlay.nix).
      # Caches and signing keys this PC may use; each key was checked against
      # real signatures from its cache on 2026-11-17.
      build.allowedSubstituters = [
        "https://cache.nixos.org"
        "https://ros.cachix.org"
        "https://cache.nixos-cuda.org"
      ];
      build.allowedPublicKeys = [
        "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
        "ros.cachix.org-1:dSyZxI8geDCJrwgvCOHDoAfOm5sV1wCPjBkKL+38Rvo="
        "cache.nixos-cuda.org:74DUi4Ye579gUqzH4ziL9IyiJBlDpMRn9MBN8oNan9M="
      ];

      # Your choices (2026-11-17):
      network.closeSsh = true; # never SSH in: port 22 only from this PC
      network.localOnly.tcp = [ 11434 ]; # Ollama API: this PC + Docker containers only
      network.localOnly.tcpRanges = [ { from = 21115; to = 21119; } ]; # RustDesk relay: unused
      network.localOnly.udp = [ 21116 ];
      network.dockerLocalOnly = true; # Open WebUI / gpt-researcher on 127.0.0.1 only
      network.ollamaLocalOrigins = true; # web pages can no longer call Ollama

      # Nightly auto-update runs the build gate first (default).
      gate.autoUpgrade = true;
    };
  };
}
