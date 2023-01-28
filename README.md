## SymbolBalloon

plugin for Sublime Text 4

ST4085+

![repository-open-graph-template](https://user-images.githubusercontent.com/123632250/215265460-83e19577-f72c-41c9-83dc-a53f9fb4b485.png)


画面上部の行が属するシンボルを表示します。


### Key Bindings

```
[
	{ "keys": ["ctrl+up"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Raise Balloon.sublime-macro"} },
	{ "keys": ["ctrl+down"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Break Balloon.sublime-macro"} },
]
```


同梱のマクロを呼び出すと、スクロールしながらシンボルを表示/消去します。


#### 単独動作の場合

```
[
	{ "keys": ["  "], "command": "raise_symbol_balloon" },
	{ "keys": ["  "], "command": "break_symbol_balloon" },
]
```


### Settings

"popup_mode"　は動作不安定です。
