{ inputs, ... }:
{
  # MangoWM (dwl-based Wayland compositor) - replaces niri as the session.
  # niri.nix is kept in the repo, just no longer imported by the host.
  flake.modules = {
    # System Aspect
    nixos.mango = { pkgs, lib, ... }: {
      imports = [ inputs.mangowm.nixosModules.mango ];

      programs.mango.enable = true; # also adds the "mango" login entry, portals, XWayland

      services.displayManager.defaultSession = lib.mkForce "mango";

      environment.systemPackages = [
        inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default
        pkgs.fuzzel
        pkgs.wl-clipboard
        pkgs.alacritty
        pkgs.apple-cursor
        pkgs.wlr-randr # check monitor names for monitor_rule
      ];
    };

    # Home Manager Aspect (same settings as the old niri config.kdl)
    homeManager.mango = { ... }: {
      xdg.configFile."mango/config.conf".text = ''
        # Autostart
        exec_once=noctalia
        exec_once=mailspring

        # Cursor (niri: xcursor-theme "macOS", size 24)
        # niri fork features shake-to-enlarge and magnifier have no mango equivalent
        cursor_theme=macOS
        cursor_size=24
        env=XCURSOR_THEME,macOS
        env=XCURSOR_SIZE,24

        # Input (focus-follows-mouse was off in niri)
        sloppy_focus=0
        xkb_rules_layout=us,th
        xkb_rules_options=grp:alt_shift_toggle

        # Focus ring -> window border (niri focus-ring width 4)
        border_px=4
        focus_color=0x7fc8ffff
        border_color=0x505050ff
        urgent_color=0x9b0000ff

        # Scrolling layout like niri on every tag
        scroller_proportion_preset=0.333,0.5,0.667
        scroller_default_proportion=0.5
        tag_rule=id:1,layout_name:scroller
        tag_rule=id:2,layout_name:scroller
        tag_rule=id:3,layout_name:scroller
        tag_rule=id:4,layout_name:scroller
        tag_rule=id:5,layout_name:scroller
        tag_rule=id:6,layout_name:scroller
        tag_rule=id:7,layout_name:scroller
        tag_rule=id:8,layout_name:scroller
        tag_rule=id:9,layout_name:scroller

        # Dual Monitor Configuration
        monitor_rule=name:^DP-2$,width:1920,height:1080,refresh:143.981,x:0,y:0,scale:1.0
        monitor_rule=name:^HDMI-A-1$,width:3840,height:2160,refresh:144.001,x:1920,y:0,scale:1.75

        # Keybindings (Mod = SUPER)
        bind=SUPER,t,spawn,alacritty
        bind=SUPER,space,spawn,fuzzel
        bind=SUPER,q,killclient

        bind=SUPER,Left,focusdir,left
        bind=SUPER,Right,focusdir,right
        bind=SUPER,Down,focusdir,down
        bind=SUPER,Up,focusdir,up

        # Mod+wheel: switch workspace (tags) / columns; cooldown 150 ms like niri
        axis_bind_apply_timeout=150
        axisbind=SUPER,DOWN,viewtoright,0
        axisbind=SUPER,UP,viewtoleft,0
        axisbind=SUPER,RIGHT,focusdir,right
        axisbind=SUPER,LEFT,focusdir,left

        bind=SUPER+SHIFT,Left,exchange_client,left
        bind=SUPER+SHIFT,Right,exchange_client,right
        bind=SUPER+SHIFT,Down,exchange_client,down
        bind=SUPER+SHIFT,Up,exchange_client,up

        bind=SUPER,r,switch_proportion_preset
        bind=SUPER+SHIFT,f,set_proportion,1.0
        bind=SUPER,f,togglemaximizescreen

        bind=SUPER,1,view,1,0
        bind=SUPER,2,view,2,0
        bind=SUPER,3,view,3,0
        bind=SUPER,4,view,4,0
        bind=SUPER+SHIFT,1,tag,1,0
        bind=SUPER+SHIFT,2,tag,2,0

        bind=SUPER+SHIFT,e,quit
      '';
    };
  };
}
