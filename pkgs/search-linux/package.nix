{ lib, stdenvNoCC, python3, makeWrapper, wrapGAppsHook4, gobject-introspection, gtk4, libadwaita, webkitgtk_6_0,
  glib-networking, gst_all_1 }:
let
  py = python3.withPackages (ps: [ ps.pygobject3 ]);
in
stdenvNoCC.mkDerivation {
  pname = "search-linux";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./search_linux.py ./searchcore.py ./selftest.py ./icons ./search-linux.svg
      ./local.searchlinux.Search.desktop ./LICENSE ./LICENSE.upstream ./README.md ];
  };
  nativeBuildInputs = [ makeWrapper wrapGAppsHook4 gobject-introspection ];
  buildInputs = [ gtk4 libadwaita webkitgtk_6_0 glib-networking ]
    ++ (with gst_all_1; [ gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-libav ]);
  dontWrapGApps = true;
  installPhase = ''
    runHook preInstall
    install -Dm644 search_linux.py searchcore.py selftest.py -t $out/share/search-linux
    cp -r icons $out/share/search-linux/icons
    install -Dm644 search-linux.svg $out/share/icons/hicolor/scalable/apps/local.searchlinux.Search.svg
    install -Dm644 local.searchlinux.Search.desktop -t $out/share/applications
    install -Dm644 LICENSE LICENSE.upstream README.md -t $out/share/doc/search-linux
    runHook postInstall
  '';
  postFixup = ''
    makeWrapper ${py}/bin/python3 $out/bin/search-linux \
      --add-flags $out/share/search-linux/search_linux.py "''${gappsWrapperArgs[@]}"
  '';
  meta = {
    description = "Search (Linux port): an unofficial WebKitGTK port of the Search browser by Office Commun";
    homepage = "https://github.com/driceroland/Search";
    license = lib.licenses.mit;
    mainProgram = "search-linux";
    platforms = lib.platforms.linux;
  };
}
