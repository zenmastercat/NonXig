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
        # BEEP: as in macOS /etc/zshrc
        setOptions = [ "INTERACTIVE_COMMENTS" "AUTO_CD" "CORRECT" "BEEP" ];
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
          # macOS-style prompt (PS1="%n@%m %1~ %# "): current folder only, plus git branch
          PROMPT='%F{green}%n@%m%f %F{blue}%1~%f''${vcs_info_msg_0_} %# '

          # From macOS /etc/zshrc (apple-oss-distributions/zsh, tag zsh-118).
          # Skipped: `disable log` (only for macOS /usr/bin/log), path_helper (macOS-only).
          [[ ''${LC_ALL:-''${LC_CTYPE:-$LANG}} == *UTF-8* ]] && setopt COMBINING_CHARS
          [[ -n $terminfo[kdch1] ]] && bindkey "$terminfo[kdch1]" delete-char
          [[ -n $terminfo[khome] ]] && bindkey "$terminfo[khome]" beginning-of-line
          [[ -n $terminfo[kend] ]] && bindkey "$terminfo[kend]" end-of-line
          [[ -n $terminfo[kcuu1] ]] && bindkey "$terminfo[kcuu1]" up-line-or-search
          [[ -n $terminfo[kcud1] ]] && bindkey "$terminfo[kcud1]" down-line-or-search
          # keypad mode while editing, so the terminal sends the terminfo key codes bound above
          if (( $+terminfo[smkx] && $+terminfo[rmkx] )); then
            zle-line-init() { echoti smkx }
            zle-line-finish() { echoti rmkx }
            zle -N zle-line-init
            zle -N zle-line-finish
          fi

          # Tell foot the current folder (OSC 7), so new windows open there (foot wiki snippet)
          autoload -Uz add-zsh-hook
          osc7-pwd() {
            emulate -L zsh
            setopt extendedglob
            local LC_ALL=C
            printf '\e]7;file://%s%s\e\\' $HOST ''${PWD//(#m)([^@-Za-z&-;_~])/%''${(l:2::0:)$(([##16]#MATCH))}}
          }
          chpwd-osc7-pwd() { (( ZSH_SUBSHELL )) || osc7-pwd }
          add-zsh-hook -Uz chpwd chpwd-osc7-pwd
        '';
      };
    };
  };
}
