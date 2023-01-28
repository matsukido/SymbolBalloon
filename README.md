## SymbolBalloon

plugin for Sublime Text 4

ST4085+

画面上部の行が属するシンボルを表示します。

![名称未設定77](https://user-images.githubusercontent.com/123632250/215292627-ef418271-aa4a-4792-b7b4-db9b680fa63a.png)


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
