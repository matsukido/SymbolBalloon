## SymbolBalloon

For Sublime Text 4

Displays the symbol the row at the top of the window belongs to

![cap](https://user-images.githubusercontent.com/123632250/233623111-6da3c17f-a99c-4704-9633-12cde2b90cb4.PNG)


### Key Bindings

Call the included macro to show/hide symbols while scrolling.

```
[
	{ "keys": ["ctrl+up"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Raise Balloon.sublime-macro"} },
	{ "keys": ["ctrl+down"], "command": "run_macro_file", "args": {"file": "res://Packages/SymbolBalloon/Break Balloon.sublime-macro"} },

	// for single operation
	// { "keys": ["ctrl+j", "ctrl+q"], "command": "raise_symbol_balloon" },
	// { "keys": ["ctrl+j", "ctrl+w"], "command": "break_symbol_balloon" },

	// optional
	// { "keys": ["ctrl+j", "ctrl+r"], "command": "goto_top_level_symbol" },
	// { "keys": ["ctrl+j", "ctrl+f"], "command": "fold_to_outline" },
]
```
