{ ... }:
{
  # Yggdrasil: encrypted mesh network (https://yggdrasil-network.github.io/).
  # Gives this PC its own 200::/7 address on interface ygg0, reachable from
  # anywhere on the mesh without port forwarding. See your address with:
  #   ip -6 addr show ygg0      or      doas yggdrasilctl getSelf
  #
  # Safety:
  # - The private key is generated on first start and kept in
  #   /var/lib/yggdrasil/private.pem (root only), never in this config or the Nix store.
  # - No automatic peering with devices on the home network (multicast off),
  #   and this node does not accept peer connections (Listen empty).
  # - Every new incoming connection on ygg0 is dropped, so ports opened for the
  #   home network (printing, Steam, ...) are NOT reachable over the mesh.
  #   To host something over Yggdrasil, add its port to yggdrasilAllowedTCPPorts below.
  flake.modules.nixos.yggdrasil = { lib, pkgs, ... }:
    let
      ifName = "ygg0";
      # Ports reachable over Yggdrasil (empty = nothing).
      yggdrasilAllowedTCPPorts = [ ];
      allowRules = lib.concatMapStrings
        (p: "ip6tables -A npb-ygg-in -p tcp --dport ${toString p} -j RETURN\n")
        yggdrasilAllowedTCPPorts;
    in
    {
      services.yggdrasil = {
        enable = true;
        persistentKeys = true;
        settings = {
          IfName = ifName;
          # 3 peers near Thailand, 100% 7-day uptime, three different operators
          # (https://publicpeers.neilalexander.dev/, checked 2026-11-18).
          Peers = [
            "tls://asia.deinfra.org:15015" # Singapore
            "tls://yg-sin.magicum.net:23900" # Singapore
            "tls://ygg5.mk16.de:1338?key=0000009611ae5391dc0aceea9f3fa6a0dc1279f4306059339e84bfb8b74d2f9b" # Hong Kong
          ];
          Listen = [ ];
          MulticastInterfaces = [ ];
          NodeInfoPrivacy = true; # don't share version/platform info
        };
      };

      environment.systemPackages = [ pkgs.yggdrasil ]; # yggdrasilctl

      # Drop all new incoming traffic on ygg0 (answers to our own connections pass).
      networking.firewall.extraCommands = ''
        ip6tables -N npb-ygg-in 2>/dev/null || ip6tables -F npb-ygg-in
        ip6tables -A npb-ygg-in -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
        ip6tables -A npb-ygg-in -p ipv6-icmp --icmpv6-type echo-request -j DROP
        ip6tables -A npb-ygg-in -p ipv6-icmp -j RETURN
        ${allowRules}ip6tables -A npb-ygg-in -j DROP
        while ip6tables -D nixos-fw -i ${ifName} -j npb-ygg-in 2>/dev/null; do :; done
        ip6tables -I nixos-fw 1 -i ${ifName} -j npb-ygg-in
        while ip6tables -D FORWARD -i ${ifName} -m conntrack ! --ctstate ESTABLISHED,RELATED -j DROP 2>/dev/null; do :; done
        ip6tables -I FORWARD 1 -i ${ifName} -m conntrack ! --ctstate ESTABLISHED,RELATED -j DROP
      '';
      networking.firewall.extraStopCommands = ''
        while ip6tables -D nixos-fw -i ${ifName} -j npb-ygg-in 2>/dev/null; do :; done
        while ip6tables -D FORWARD -i ${ifName} -m conntrack ! --ctstate ESTABLISHED,RELATED -j DROP 2>/dev/null; do :; done
        ip6tables -F npb-ygg-in 2>/dev/null || true
        ip6tables -X npb-ygg-in 2>/dev/null || true
      '';
    };
}
