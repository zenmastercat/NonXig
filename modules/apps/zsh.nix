{ ... }:
{
  flake.modules = {
    # NixOS aspect: Registers zsh in /etc/shells and sets login shell
    nixos.zsh = { pkgs, ... }: {
      programs.zsh.enable = true;
      users.users.lucas.shell = pkgs.zsh;
      # completions for system packages
      environment.pathsToLink = [ "/share/zsh" ];
    };

    # Home Manager aspect: zsh configuration (bash-style syntax, so pasted commands work)
    homeManager.zsh = { ... }: {
      programs.zsh = {
        enable = true;
        enableCompletion = true;
        autosuggestion.enable = true; # grey suggestions from history, accept with →
        syntaxHighlighting.enable = true;
        history = {
          size = 50000;
          save = 50000;
          ignoreDups = true;
          share = true;
        };
        # INTERACTIVE_COMMENTS: pasted commands with "# comments" run; CORRECT: offer fixes for mistyped commands
        setOptions = [ "INTERACTIVE_COMMENTS" "AUTO_CD" "CORRECT" ];
        # uv tools (graphify), same as the old fish conf.d snippet
        envExtra = ''
          export PATH="$HOME/.local/bin:$PATH"
        '';
        initContent = ''
          autoload -Uz vcs_info
          precmd() { vcs_info }
          zstyle ':vcs_info:git:*' formats ' %F{yellow}(%b)%f'
          setopt PROMPT_SUBST
          # autocorrect question: y = use fix, n = keep, a = abort, e = edit
          SPROMPT='zsh: correct %F{red}%R%f to %F{green}%r%f? [nyae] '
          PROMPT='%F{green}%n@%m%f %F{blue}%~%f''${vcs_info_msg_0_} %# '
        '';
      };
    };
  };
}
