{ inputs, ... }:
{
  flake.modules.nixos.hermes = { pkgs, ... }:
    let
      hermes = inputs.hermes-agent.packages.${pkgs.stdenv.hostPlatform.system};
      # The flake stamps 0.0.0 by default; stamp the real release so OpenBot reads it.
      # Keep this equal to the tag in flake.nix (hermes-agent.url).
      hermes-cli = hermes.default.override { version = "0.22.7"; };
    in
    {
      # Hermes Agent (Nous Research). Its settings, sign-in, memories and chats stay in ~/.hermes.
      environment.systemPackages = [
        hermes-cli     # CLI: `hermes`, `hermes-agent`, `hermes-acp` (OpenBot uses `hermes acp`)
        hermes.desktop # desktop app: "Hermes" in the menu, or `hermes-desktop`
      ];
    };
}
