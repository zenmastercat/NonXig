{ inputs, ... }:
{
  flake.modules.nixos.openbot = { pkgs, ... }:
    let
      pname = "openbot";
      version = "0.75.0";
      src = pkgs.fetchurl {
        url = "https://github.com/nightly-labs/openbot/releases/download/v${version}/OpenBot-${version}-x86_64.AppImage";
        hash = "sha256-0wSli2ZAYsYCMgQU3mgX6MrB3WMYjx7Qeuvrh1W8V2o=";
      };
      contents = pkgs.appimageTools.extractType2 { inherit pname version src; };
      openbot-unwrapped = pkgs.appimageTools.wrapType2 {
        inherit pname version src;
        # Menu entry, openbot:// links and icon from the AppImage.
        extraInstallCommands = ''
          install -Dm444 ${contents}/openbot.desktop $out/share/applications/openbot.desktop
          substituteInPlace $out/share/applications/openbot.desktop \
            --replace-fail 'Exec=AppRun' 'Exec=openbot'
          install -Dm444 ${contents}/openbot.png $out/share/pixmaps/openbot.png
        '';
      };

      # Hermes Agent from its flake, the same build as hermes.nix.
      hermes = inputs.hermes-agent.packages.${pkgs.stdenv.hostPlatform.system}.default.override {
        version = "0.22.7"; # keep equal to the tag in flake.nix
      };

      # OpenBot wrapped with Hermes first on its PATH, so its Hermes provider runs this
      # Nix copy and not the script install in ~/.local/bin.
      openbot = pkgs.symlinkJoin {
        name = "openbot-${version}";
        paths = [ openbot-unwrapped ];
        nativeBuildInputs = [ pkgs.makeWrapper ];
        postBuild = ''
          wrapProgram $out/bin/openbot --prefix PATH : ${hermes}/bin
        '';
      };
    in
    {
      environment.systemPackages = [ openbot ];
    };
}
