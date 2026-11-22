{ inputs, ... }:
{
  flake.modules.nixos.t3code = { pkgs, ... }:
    let
      # T3 Code from current nixos-unstable, without updating the rest of the system.
      unstable = import inputs.nixpkgs-t3 {
        system = pkgs.stdenv.hostPlatform.system;
        config.allowUnfree = true; # claude-code is unfree
      };
    in
    {
      environment.systemPackages = [
        unstable.t3code      # the app; start it with: t3code-desktop
        unstable.claude-code # the Claude agent T3 Code drives
        unstable.codex       # the Codex agent T3 Code drives
      ];

      # Stop T3 Code's usage statistics (sent to ingest.t3.codes by default).
      environment.sessionVariables.T3CODE_TELEMETRY_ENABLED = "false";
    };
}
