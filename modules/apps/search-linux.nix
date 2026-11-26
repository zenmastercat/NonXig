{ ... }:
{
  # Search (Linux port): unofficial GTK4 + WebKitGTK port of the Search browser by Office Commun (MIT).
  # Source lives in pkgs/search-linux (copied from ~/Projects/search-linux). Start it from the app menu or: search-linux
  flake.modules.nixos.search-linux = { pkgs, ... }: {
    environment.systemPackages = [ (pkgs.callPackage ../../pkgs/search-linux/package.nix { }) ];
  };
}
