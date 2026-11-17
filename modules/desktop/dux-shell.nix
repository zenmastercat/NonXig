{ inputs, ... }:
{
  # Dux Shell (github:duxlabs-dev/dux-shell) replaces Noctalia,
  # dux-greeter (github:duxlabs-dev/dux-greeter, on greetd) replaces SDDM.
  # Started by mango (exec_once=dms run in mango.nix).
  flake.modules = {
    # System Aspect
    nixos.dux-shell = { pkgs, ... }:
      let
        system = pkgs.stdenv.hostPlatform.system;
      in
      {
        imports = [
          inputs.dms.nixosModules.default
          inputs.dank-greeter.nixosModules.default
        ];

        programs.dank-material-shell = {
          enable = true;
          # Built by the dms flake on nixpkgs-unstable (needs Go 1.27)
          package = inputs.dms.packages.${system}.dms-shell;
        };

        # Login screen: greetd + dms-greeter running inside mango
        programs.dms-greeter = {
          enable = true;
          package = inputs.dank-greeter.packages.${system}.dms-greeter;
          compositor.name = "mango";
          configHome = "/home/lucas"; # login screen follows your Dux Shell theme/wallpaper
          # Mango config for the login screen (the greeter user has no ~/.config/mango,
          # so without this mango reports it cannot open its config)
          compositor.customConfig = ''
            monitor_rule=name:^DP-2$,width:1920,height:1080,refresh:143.981,x:0,y:0,scale:1.0
            monitor_rule=name:^HDMI-A-1$,width:3840,height:2160,refresh:144.001,x:1920,y:0,scale:1.75
            xkb_rules_layout=us,th
            xkb_rules_options=grp:alt_shift_toggle
            cursor_theme=macOS
            cursor_size=24
            env=XCURSOR_THEME,macOS
            env=XCURSOR_SIZE,24
          '';
        };
      };

    # Home Manager Aspect: Anthropic Sans as the Dux Shell main font.
    # Only set when no font is chosen yet, so Dux Shell's Settings can still change it.
    homeManager.dux-shell = { pkgs, lib, config, ... }: {
      home.activation.duxShellFont = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        if [[ ! -v DRY_RUN ]]; then
          f="${config.xdg.configHome}/dms/settings.json"
          mkdir -p "$(dirname "$f")"
          [ -s "$f" ] || echo '{}' > "$f"
          tmp="$(mktemp)"
          if ${pkgs.jq}/bin/jq 'if has("fontFamily") then . else . + {fontFamily: "AnthropicSans"} end' "$f" > "$tmp"; then
            mv "$tmp" "$f"
          else
            rm -f "$tmp"
          fi
        fi
      '';
    };
  };
}
