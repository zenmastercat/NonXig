{ inputs, ... }:
{
  flake.modules.nixos.herdr = { pkgs, lib, ... }:
    let
      # herdr TUI from current nixos-unstable (same input as T3 Code).
      unstable = inputs.nixpkgs-t3.legacyPackages.${pkgs.stdenv.hostPlatform.system};

      # herdr-core (`hc`): the background runtime the desktop app talks to. Static binary.
      herdr-core = pkgs.stdenvNoCC.mkDerivation rec {
        pname = "herdr-core";
        version = "0.1.21";
        src = pkgs.fetchurl {
          url = "https://releases.herdr.dev/core/${version}/herdr-core-linux-x86_64.tar.gz";
          hash = "sha256-eEJHVcEKQN3jigvbVcIKwZcG6a4F7Wj8Ks8fz/DZQcE=";
        };
        sourceRoot = ".";
        installPhase = ''
          install -Dm755 herdr-core $out/bin/herdr-core
          ln -s herdr-core $out/bin/hc
        '';
      };

      # Herdr desktop app.
      herdr-app = pkgs.stdenv.mkDerivation rec {
        pname = "herdr-app";
        version = "0.1.16";
        src = pkgs.fetchurl {
          url = "https://releases.herdr.dev/app/${version}/herdr-app-linux-x86_64.tar.gz";
          hash = "sha256-KC0mMhlrI4IGz+Zr+2HA+vKZyhyRhDvQdlIbvjZXEhY=";
        };
        nativeBuildInputs = [ pkgs.autoPatchelfHook pkgs.makeWrapper ];
        buildInputs = [ pkgs.libxcb pkgs.libxkbcommon pkgs.stdenv.cc.cc.lib ];
        # Loaded at runtime (GPU drawing, Wayland, keyboard).
        runtimeLibs = with pkgs; [ libGL vulkan-loader wayland libxkbcommon libxcb ];
        installPhase = ''
          install -Dm755 herdr-app $out/bin/herdr-app
          install -Dm444 herdr-app.svg $out/share/icons/hicolor/scalable/apps/herdr-app.svg
          wrapProgram $out/bin/herdr-app \
            --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath runtimeLibs} \
            --prefix PATH : ${herdr-core}/bin
          mkdir -p $out/share/applications
          cat > $out/share/applications/herdr-app.desktop <<DESKTOP
        [Desktop Entry]
        Type=Application
        Name=Herdr
        Comment=Terminals and coding agents that keep running
        Exec=$out/bin/herdr-app
        Icon=herdr-app
        Terminal=false
        Categories=Development;
        StartupWMClass=herdr-app
        DESKTOP
          sed -i 's/^ *//' $out/share/applications/herdr-app.desktop
        '';
      };
    in
    {
      environment.systemPackages = [
        unstable.herdr # terminal app: run `herdr`
        herdr-app      # desktop app: "Herdr" in the menu, or `herdr-app`
        herdr-core     # `herdr-core` / `hc`
      ];
    };
}
