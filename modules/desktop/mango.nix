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
        # inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default # unwired: Dux Shell replaces Noctalia
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
        # exec_once=noctalia  (unwired: Dux Shell replaces Noctalia)
        # Dux Shell; exec_once, not exec: mango re-runs exec= on every reload
        exec_once=dms run
        exec_once=mailspring

        # Dux Shell detects the compositor from this
        env=XDG_CURRENT_DESKTOP,mango
        env=XDG_SESSION_TYPE,wayland

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

        # ===== MangoWM default keybindings (mango assets/config.conf) =====
        # Only change from upstream: rofi -> Dux Shell launcher (terminal is foot, as upstream)
        # (rofi is not installed).
        # key name refer to `xev` or `wev` command output,
        # mod keys name: super,ctrl,alt,shift,none

        # reload config
        bind=SUPER,r,reload_config

        # menu and terminal
        bind=Alt,space,spawn,dms ipc call spotlight toggle
        bind=Alt,Return,spawn,foot

        # exit
        bind=SUPER,m,quit
        bind=ALT,q,killclient,

        # switch window focus
        bind=SUPER,Tab,focusstack,next
        bind=ALT,Left,focusdir,left
        bind=ALT,Right,focusdir,right
        bind=ALT,Up,focusdir,up
        bind=ALT,Down,focusdir,down

        # move window
        bind=SUPER+SHIFT,Up,move_client,up
        bind=SUPER+SHIFT,Down,move_client,down
        bind=SUPER+SHIFT,Left,move_client,left
        bind=SUPER+SHIFT,Right,move_client,right

        # switch window status
        bind=SUPER,g,toggleglobal,
        bind=ALT,Tab,togglejump,
        bind=ALT,backslash,togglefloating,
        bind=ALT,a,togglemaximizescreen,
        bind=ALT,f,togglefullscreen,
        bind=ALT+SHIFT,f,togglefakefullscreen,
        bind=SUPER,i,minimized,
        bind=SUPER,o,toggleoverlay,
        bind=SUPER+SHIFT,I,restore_minimized
        bind=ALT,z,toggle_scratchpad

        # scroller layout
        bind=ALT,e,set_proportion,1.0
        bind=ALT,x,switch_proportion_preset,
        bind=alt+super+ctrl,Left,scroller_stack,left
        bind=alt+super+ctrl,Right,scroller_stack,right
        bind=alt+super+ctrl,Up,scroller_stack,up
        bind=alt+super+ctrl,Down,scroller_stack,down

        #dwindle layout(manual split mode)
        bind=alt+shift,Return,dwindle_toggle_split_direction

        # switch layout
        bind=SUPER,n,switch_layout

        # tag switch
        bind=SUPER,Left,viewtoleft,0
        bind=CTRL,Left,viewtoleft_have_client,0
        bind=SUPER,Right,viewtoright,0
        bind=CTRL,Right,viewtoright_have_client,0
        bind=CTRL+SUPER,Left,tagtoleft,0
        bind=CTRL+SUPER,Right,tagtoright,0

        bind=Ctrl,1,view,1,0
        bind=Ctrl,2,view,2,0
        bind=Ctrl,3,view,3,0
        bind=Ctrl,4,view,4,0
        bind=Ctrl,5,view,5,0
        bind=Ctrl,6,view,6,0
        bind=Ctrl,7,view,7,0
        bind=Ctrl,8,view,8,0
        bind=Ctrl,9,view,9,0

        # tag: move client to the tag and focus it
        # tagsilent: move client to the tag and not focus it
        # bind=Alt,1,tagsilent,1
        bind=Alt,1,tag,1,0
        bind=Alt,2,tag,2,0
        bind=Alt,3,tag,3,0
        bind=Alt,4,tag,4,0
        bind=Alt,5,tag,5,0
        bind=Alt,6,tag,6,0
        bind=Alt,7,tag,7,0
        bind=Alt,8,tag,8,0
        bind=Alt,9,tag,9,0

        # monitor switch
        bind=alt+shift,Left,focusmon,left
        bind=alt+shift,Right,focusmon,right
        bind=SUPER+Alt,Left,tagmon,left
        bind=SUPER+Alt,Right,tagmon,right

        # gaps
        bind=ALT+SHIFT,X,incgaps,1
        bind=ALT+SHIFT,Z,incgaps,-1
        bind=ALT+SHIFT,R,togglegaps

        # movewin
        bind=CTRL+SHIFT,Up,movewin,+0,-50
        bind=CTRL+SHIFT,Down,movewin,+0,+50
        bind=CTRL+SHIFT,Left,movewin,-50,+0
        bind=CTRL+SHIFT,Right,movewin,+50,+0

        # resizewin
        bind=CTRL+ALT,Up,resizewin,+0,-50
        bind=CTRL+ALT,Down,resizewin,+0,+50
        bind=CTRL+ALT,Left,resizewin,-50,+0
        bind=CTRL+ALT,Right,resizewin,+50,+0

        # Mouse Button Bindings
        # btn_left and btn_right can't bind none mod key
        mousebind=SUPER,btn_left,moveresize,curmove
        mousebind=NONE,btn_middle,togglemaximizescreen,0
        mousebind=SUPER,btn_right,moveresize,curresize

        # Axis Bindings
        axisbind=SUPER,UP,viewtoleft_have_client
        axisbind=SUPER,DOWN,viewtoright_have_client

        # Gesture Bindings
        gesturebind=none,left,3,focusdir,left
        gesturebind=none,right,3,focusdir,right
        gesturebind=none,up,3,focusdir,up
        gesturebind=none,down,3,focusdir,down
        gesturebind=none,right,4,viewprev_have_client
        gesturebind=none,left,4,viewnext_have_client
        gesturebind=none,up,4,enteroverview
        gesturebind=none,down,4,leaveoverview
      '';
    };
  };
}
