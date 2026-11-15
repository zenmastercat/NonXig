{ inputs, ... }:
{
  # Anthropic fonts (github:matthieuhuguet/anthropic-fonts) as the Noctalia font.
  # Families: AnthropicSans, AnthropicSerif, AnthropicMono
  flake.modules = {
    # System Aspect: install the TTFs
    nixos.anthropic-fonts = { pkgs, ... }: {
      fonts.packages = [
        (pkgs.runCommand "anthropic-fonts" { } ''
          install -Dm644 ${inputs.anthropic-fonts}/ttf/*.ttf -t $out/share/fonts/truetype/anthropic
        '')
      ];
    };

    # Home Manager Aspect: Noctalia main font (~/.config/noctalia/config.toml)
    homeManager.anthropic-fonts = { pkgs, ... }: {
      imports = [ inputs.noctalia.homeModules.default ];

      programs.noctalia = {
        enable = true;
        package = inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default;
        settings.shell.font_family = "AnthropicSans";
      };
    };
  };
}
