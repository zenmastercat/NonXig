# { config, inputs, ... }:
# let
#   inherit (config.flake.modules) nixos homeManager;
# in
# {
#   # NixOS Configuration Target
#   configurations.nixos.nixos.module = {
#     _module.args = { inherit inputs; };
#     imports = [
#       nixos.system
#       nixos.hardware
#       nixos.auto-updates
#       nixos.applications
#       nixos.additional-services
#       nixos.ros
#       nixos.fish
#     ];
#   };

#   # 2. User-level Home Manager Configuration
#   home-manager.useGlobalPkgs = true;
#   home-manager.useUserPackages = true;

#   # Home Manager Profile Target
#   configurations.homeManager.myprofile.module = {
#     imports = [
#       homeManager.fish
#       homeManager.myprofile
#       homeManager.kitty
#     ];
#   };
# }

{ config, inputs, ... }:
let
  inherit (config.flake.modules) nixos homeManager;
in
{
  # NixOS Configuration Target
  configurations.nixos."nixos-btw".module = {
    _module.args = { inherit inputs; };
    boot.loader = {
      systemd-boot.enable = false;
      efi.canTouchEfiVariables = false;
      grub = {
        enable = true;
        device = "nodev";
        efiSupport = true;
        efiInstallAsRemovable = true;
      };
    };
    
    imports = [
      # 1. Import Home Manager's NixOS module so NixOS recognizes 'home-manager.*' options
      inputs.home-manager.nixosModules.home-manager

      # 2. NixOS System Aspects
      nixos.system
      nixos.hardware
      nixos.auto-updates
      nixos.applications
      nixos.additional-services
      nixos.yggdrasil # Yggdrasil mesh network (incoming blocked)
      nixos.ros
      nixos.zsh # zsh replaces fish (fish.nix kept, unwired)
      nixos.mango
      nixos.anthropic-fonts
      nixos.dux-shell # Dux Shell + dux-greeter (greetd)
      nixos.bongo-keyfeed # masked key feed for the Bongo Cat plugin
      nixos.protect-barrior # Nix-Protect-Barrior security layer
      nixos.ai-privacy # AI privacy proxy: redacts secrets in AI API requests
      # nixos.sddm # unwired: dux-greeter replaces SDDM (sddm.nix kept)
    ];

    # 3. Home Manager Configuration (Moved inside NixOS module)
    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
      backupFileExtension = "backup";
      users.lucas = {
        imports = [
          homeManager.zsh
          homeManager.myprofile
          homeManager.foot
          homeManager.mango
          homeManager.anthropic-fonts
          homeManager.dux-shell
        ];
      };
    };
  };

  # Standalone Home Manager target (if building HM separately outside NixOS rebuilds)
  configurations.homeManager.myprofile.module = {
    imports = [
      homeManager.zsh
      homeManager.myprofile
      homeManager.foot
      homeManager.mango
      homeManager.anthropic-fonts
      homeManager.dux-shell
    ];
  };
}
