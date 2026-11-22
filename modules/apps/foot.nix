{ ... }:
{
  flake.modules = {
    # Home Manager Aspect (Terminal config, font, opacity) — same look as the old kitty.nix
    homeManager.foot = { pkgs, ... }: {
      programs.foot = {
        enable = true;
        settings = {
          main = {
            shell = "${pkgs.zsh}/bin/zsh";
            font = "JetBrainsMono Nerd Font:size=12";
            include = "${pkgs.foot.themes}/share/foot/themes/gruvbox-dark";
          };
          # foot >= 1.24 names the colour section colors-dark
          colors-dark.alpha = 0.75;
        };
      };
    };

    # NixOS Aspect (System-level package install)
    nixos.foot = { pkgs, ... }: {
      environment.systemPackages = [ pkgs.foot ];
    };
  };
}
