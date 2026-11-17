{ ... }:
{
  flake.modules.nixos.virtualbox-guest = { pkgs, ... }: {
    virtualisation.virtualbox = {
      host = {
        enable = true;
        enableExtensionPack = true;
      };
    };
  };
}
