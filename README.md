## SymbolBalloon

For Sublime Text 4

Displays the symbol the row at the top of the window belongs to

![cap](https://user-images.githubusercontent.com/123632250/233623111-6da3c17f-a99c-4704-9633-12cde2b90cb4.PNG)


### Key Bindings

```
[
	// to show/hide symbols while scrolling.
	{ "keys": ["ctrl+up"], 
		"command": "chain",
		"args": {
			"commands": [
				["raise_symbol_balloon"],
				["scroll_lines" , {"amount": 1.0 } ],
			]
		}
	},
	{ "keys": ["ctrl+down"], 
		"command": "chain",
		"args": {
			"commands": [
				["break_symbol_balloon"],
				["scroll_lines" , {"amount": -1.0 } ],
			]
		}
	},

	// for single operation
	// { "keys": ["ctrl+j", "ctrl+q"], "command": "raise_symbol_balloon" },
	// { "keys": ["ctrl+j", "ctrl+w"], "command": "break_symbol_balloon" },

	// optional
	// { "keys": ["ctrl+j", "ctrl+f"], "command": "fold_to_outline" },
	// { "keys": ["ctrl+j", "ctrl+r"], "command": "goto_top_level_symbol" },
]
```

### Installation

- Code > Download ZIP
- Unzip and change the folder name to "SymbolBalloon"
- (ST Menu) Preferences > Browse Packages
- Move SymbolBalloon folder to the folder that appears