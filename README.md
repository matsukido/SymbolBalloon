## SymbolBalloon

Sublime Text 4085+

画面上部の行が属するシンボルを表示します。

![キャプeeeチャ](https://user-images.githubusercontent.com/123632250/225626963-f59b87a5-3fd4-4a3d-a47b-50211db2f0da.PNG)


### Key Bindings

```
[
	{ "keys": ["ctrl+up"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Raise Balloon.sublime-macro"} },
	{ "keys": ["ctrl+down"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Break Balloon.sublime-macro"} },

	// optional
	// { "keys": ["ctrl+j", "ctrl+r"], "command": "goto_top_level_symbol" },
	// { "keys": ["ctrl+j", "ctrl+f"], "command": "fold_to_outline" },
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
