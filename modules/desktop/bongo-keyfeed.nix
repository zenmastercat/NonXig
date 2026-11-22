{ ... }:
{
  # Masked keyboard feed for the Dux Shell "Bongo Cat" plugin.
  #
  # The plugin runs `libinput debug-events --show-keycodes` and normally needs the
  # user in the `input` group, which would let every program the user runs read
  # every keystroke (passwords included). Instead, a small socket-activated service
  # reads the keyboard with its own throwaway user and passes on only what the cat
  # needs: letters, digits and symbols all become KEY_A; space, enter, backspace,
  # delete, F-keys, modifiers and navigation keys keep their names; mouse clicks
  # keep left/right/middle. Device names and timestamps are dropped.
  #
  # A `libinput` wrapper on PATH sends `libinput debug-events` from normal users to
  # that socket; every other libinput command (and root) uses the real tool.
  flake.modules.nixos.bongo-keyfeed = { pkgs, lib, ... }:
    let
      sock = "/run/bongo-keyfeed.sock";
      realLibinput = "${pkgs.libinput.bin}/bin/libinput";

      filter = pkgs.writeText "bongo-keyfeed.awk" ''
        BEGIN {
          n = split("KEY_SPACE KEY_ENTER KEY_KPENTER KEY_BACKSPACE KEY_DELETE " \
                    "KEY_LEFTSHIFT KEY_RIGHTSHIFT KEY_LEFTCTRL KEY_RIGHTCTRL " \
                    "KEY_LEFTALT KEY_RIGHTALT KEY_LEFTMETA KEY_RIGHTMETA " \
                    "KEY_CAPSLOCK KEY_NUMLOCK KEY_SCROLLLOCK KEY_UP KEY_DOWN " \
                    "KEY_LEFT KEY_RIGHT KEY_PAGEUP KEY_PAGEDOWN KEY_HOME KEY_END " \
                    "KEY_ESC KEY_PAUSE KEY_PRINT KEY_INSERT KEY_TAB", names, " ")
          for (i = 1; i <= n; i++) keep[names[i]] = 1
        }
        /KEYBOARD_KEY/ {
          if (match($0, /KEY_[A-Z0-9_]+ \([0-9]+\)/)) {
            k = substr($0, RSTART, RLENGTH)
            split(k, part, " ")
            if (!(part[1] in keep) && part[1] !~ /^KEY_F[0-9]+$/) k = "KEY_A (30)"
            state = ($0 ~ / pressed/) ? "pressed" : "released"
            print "-     KEYBOARD_KEY            +0.000s\t" k " " state
            fflush()
          }
          next
        }
        /POINTER_BUTTON/ && / pressed/ {
          b = "BTN_LEFT (272)"
          if ($0 ~ /BTN_RIGHT/) b = "BTN_RIGHT (273)"
          else if ($0 ~ /BTN_MIDDLE/) b = "BTN_MIDDLE (274)"
          print "-     POINTER_BUTTON          +0.000s\t" b " pressed"
          fflush()
        }
      '';

      feed = pkgs.writeShellScript "bongo-keyfeed" ''
        ${pkgs.coreutils}/bin/stdbuf -oL ${realLibinput} debug-events --show-keycodes \
          | ${pkgs.gawk}/bin/awk -f ${filter}
      '';

      wrapper = pkgs.writeShellScriptBin "libinput" ''
        if [ "$(${pkgs.coreutils}/bin/id -u)" != 0 ] && [ "''${1-}" = debug-events ]; then
          exec ${pkgs.socat}/bin/socat -u UNIX-CONNECT:${sock} STDOUT
        fi
        exec ${realLibinput} "$@"
      '';
    in
    {
      environment.systemPackages = [ (lib.hiPrio wrapper) ];

      systemd.sockets.bongo-keyfeed = {
        description = "Masked keyboard feed for Bongo Cat";
        wantedBy = [ "sockets.target" ];
        socketConfig = {
          ListenStream = sock;
          Accept = true;
          SocketUser = "lucas";
          SocketMode = "0600";
          MaxConnections = 4;
        };
      };

      systemd.services."bongo-keyfeed@" = {
        description = "Masked keyboard feed for Bongo Cat (one per client)";
        serviceConfig = {
          ExecStart = feed;
          StandardInput = "socket";
          StandardOutput = "socket";
          StandardError = "journal";
          DynamicUser = true;
          SupplementaryGroups = [ "input" ];
          DevicePolicy = "closed";
          DeviceAllow = [ "char-input rw" ];
          NoNewPrivileges = true;
          ProtectSystem = "strict";
          ProtectHome = true;
          PrivateTmp = true;
          ProtectKernelTunables = true;
          ProtectKernelModules = true;
          ProtectKernelLogs = true;
          ProtectControlGroups = true;
          ProtectClock = true;
          ProtectHostname = true;
          ProtectProc = "invisible";
          RestrictAddressFamilies = [ "AF_UNIX" "AF_NETLINK" ];
          IPAddressDeny = "any";
          RestrictNamespaces = true;
          RestrictRealtime = true;
          RestrictSUIDSGID = true;
          LockPersonality = true;
          MemoryDenyWriteExecute = true;
          SystemCallArchitectures = "native";
          SystemCallFilter = [ "@system-service" "~@privileged" ];
          CapabilityBoundingSet = "";
          UMask = "0077";
        };
      };
    };
}
