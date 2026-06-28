# init: scaffold a Target from a plain reference function
Output "/tmp/tw_throwaway.gif"
Set FontSize 15
Set Width 1180
Set Height 380
Set Padding 22
Set Theme { "name": "tripwire", "background": "#0d0d0d", "foreground": "#f5f5f5", "cursor": "#e5484d", "selection": "#333333", "black": "#0d0d0d", "red": "#e5484d", "green": "#7bbf7b", "yellow": "#e5a04d", "blue": "#6ab0f3", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#f5f5f5", "brightBlack": "#5c5852", "brightRed": "#e5484d", "brightGreen": "#7bbf7b", "brightYellow": "#e5a04d", "brightBlue": "#6ab0f3", "brightMagenta": "#c678dd", "brightCyan": "#56b6c2", "brightWhite": "#ffffff" }

Hide
Type "export PS1='❯ '; export PATH=/Users/sammytourani/Desktop/tripwire/.venv/bin:$PATH; cd /Users/sammytourani/Desktop/tripwire; rm -f /tmp/rowsum_target.py; clear"
Enter
Sleep 1.2s
Show

Type "tripwire init /tmp/rowsum.py"
Sleep 500ms
Enter
Sleep 2.5s
Screenshot "docs/assets/cli-init.png"
