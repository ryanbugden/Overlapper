import ezui
from mojo.extensions import getExtensionDefault, setExtensionDefault

EXTENSION_KEY = 'com.ryanbugden.overlapper.settings'

class Overlapper(ezui.WindowController):

    def build(self):
        content = """
        * TwoColumnForm                     @form
        > : Hotkey:
        > [_v_]                             @hotkey
        ---
        """
        footer = """
        (Apply)                             @applyButton
        """
        descriptionData = dict(
            form=dict(
                titleColumnWidth=48,
                itemColumnWidth=48
            ),
            hotkey=dict(
                placeholder="v",
                valueType="string",
                continuous=True,
            ),
            applyButton=dict(
                keyEquivalent=chr(13),
            )
        )
        self.w = ezui.EZWindow(
            title="Settings",
            content=content,
            descriptionData=descriptionData,
            controller=self,
            footer = footer,
            size="auto"
        )

    def started(self):
        self.w.open()
        prefs = getExtensionDefault(EXTENSION_KEY, fallback=self.w.getItemValues())
        self.w.setItemValues(prefs)
        
    def hotkeyCallback(self, sender):
        hotkey = sender.get()
        if len(hotkey) > 1:
            hotkey = hotkey[-1]
            self.w.getItem("hotkey").set(hotkey.lower())

    def applyButtonCallback(self, sender):
        self.register_defaults()
        self.w.close()        

    def register_defaults(self):
        setExtensionDefault(EXTENSION_KEY, self.w.getItemValues(), validate=True)
        # Print a readout of the user’s updated Overlapper settings
        print("\nOverlapper settings:\n", getExtensionDefault(EXTENSION_KEY))  

Overlapper()