{ ... }:
{
  # AI privacy barrier: every AI tool's API traffic goes through a local proxy
  # (pkgs/ai-privacy-proxy) that replaces secrets and private terms with
  # [REDACTED:<kind>] before they leave this PC. Responses are not changed.
  #   status:  systemctl --user status ai-privacy-proxy
  #   log:     journalctl --user -u ai-privacy-proxy -f   (kinds only, never values)
  #   terms:   ~/.config/ai-privacy-proxy/private-terms.txt (one per line, not in git)
  #   bypass for one command:  env -u ANTHROPIC_BASE_URL claude ...
  flake.modules.nixos.ai-privacy = { pkgs, lib, ... }:
    let
      httpPort = 18765; # Claude Code (and OpenBot's Claude agents)
      tlsPort = 18766; # Codex: it accepts only an HTTPS ChatGPT backend
      stateDir = "/home/lucas/.local/state/ai-privacy-proxy";

      python = pkgs.python3.withPackages (ps: [ ps.aiohttp ]);

      proxy = pkgs.stdenvNoCC.mkDerivation {
        pname = "ai-privacy-proxy";
        version = "0.1.0";
        src = ../../pkgs/ai-privacy-proxy;
        nativeBuildInputs = [ pkgs.makeWrapper ];
        doCheck = true;
        checkPhase = ''
          runHook preCheck
          ${python}/bin/python -m unittest -v test_proxy
          runHook postCheck
        '';
        installPhase = ''
          install -Dm644 proxy.py $out/share/ai-privacy-proxy/proxy.py
          makeWrapper ${python}/bin/python $out/bin/ai-privacy-proxy \
            --add-flags $out/share/ai-privacy-proxy/proxy.py
        '';
      };

      config = pkgs.writeText "ai-privacy-proxy.json" (builtins.toJSON {
        listen_host = "127.0.0.1";
        listen_port = httpPort;
        tls_port = tlsPort;
        tls_cert = "${stateDir}/localhost-cert.pem";
        tls_key = "${stateDir}/localhost-key.pem";
        routes = {
          anthropic = "https://api.anthropic.com";
          backend-api = "https://chatgpt.com/backend-api";
          openai = "https://api.openai.com";
          openrouter = "https://openrouter.ai/api";
        };
        # Exact values of keys stored on this PC are redacted wherever they appear.
        secret_globs = [
          "~/.config/OpenBot/agent-api-keys/**/*"
          "~/.omniroute/.env"
          "~/.codex/auth.json"
          "~/.claude/.credentials.json"
          "~/.hermes/.env"
          "~/.hermes/auth.json"
        ];
        terms_file = "~/.config/ai-privacy-proxy/private-terms.txt";
        # Codex leaves its login off the apps-connector request when routed
        # here; the proxy adds it, only for chatgpt.com (your choice, 2026-11-22).
        codex_auth_file = "~/.codex/auth.json";
        codex_auth_prefixes = [ "/backend-api/ps/" ];
        drop_prefixes = [ "/backend-api/codex/analytics-events/" ];
      });

      # Self-signed certificate for "localhost" only (not a CA, not added to
      # the system trust store); only Codex trusts it, via CODEX_CA_CERTIFICATE.
      makeCert = pkgs.writeShellScript "ai-privacy-proxy-cert" ''
        set -eu
        umask 077
        mkdir -p ${stateDir}
        [ -s ${stateDir}/localhost-cert.pem ] && [ -s ${stateDir}/localhost-key.pem ] && exit 0
        ${pkgs.openssl}/bin/openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
          -nodes -days 3650 -subj /CN=localhost \
          -addext subjectAltName=DNS:localhost -addext basicConstraints=critical,CA:FALSE \
          -keyout ${stateDir}/localhost-key.pem -out ${stateDir}/localhost-cert.pem 2>/dev/null
        chmod 644 ${stateDir}/localhost-cert.pem
      '';
    in
    {
      environment.systemPackages = [ proxy ];

      systemd.user.services.ai-privacy-proxy = {
        description = "AI privacy proxy (redacts secrets in AI API requests)";
        wantedBy = [ "default.target" ];
        serviceConfig = {
          ExecStartPre = makeCert;
          ExecStart = "${proxy}/bin/ai-privacy-proxy ${config}";
          Restart = "always";
          RestartSec = 1;
          NoNewPrivileges = true;
          PrivateTmp = true;
          RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];
        };
      };

      environment.sessionVariables = {
        # Claude Code: API calls through the proxy; telemetry and error reports off
        # (features such as /bug and auto-compact keep working).
        ANTHROPIC_BASE_URL = "http://127.0.0.1:${toString httpPort}/anthropic";
        DISABLE_TELEMETRY = "1";
        DISABLE_ERROR_REPORTING = "1";
        # Codex: trusts the proxy's localhost certificate. Its base URL is set in
        # ~/.codex/config.toml: chatgpt_base_url = "https://localhost:18766/backend-api/"
        CODEX_CA_CERTIFICATE = "${stateDir}/localhost-cert.pem";
      };
    };
}
