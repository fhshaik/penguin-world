"""Inject Penguin World's player-card Trade action into exported AS2 source."""

import sys
from pathlib import Path


source = Path(sys.argv[1])
text = source.read_text(encoding="utf-8-sig")

function_anchor = "function showRemoveBuddyButton()\n{"
menu_anchor = "   showStampBookButton();\n   if(shell.playerModel.isPlayerModerator())"

trade_functions = r'''function hideTradeButton()
{
   PLAYER_WIDGET.art_mc.trade_mc._visible = false;
}
function showTradeButton()
{
   var card = PLAYER_WIDGET.art_mc;
   var button = card.trade_mc;
   if(button == undefined)
   {
      button = card.createEmptyMovieClip("trade_mc",card.getNextHighestDepth());
      button._x = card.report_mc._x - 20;
      button._y = card.report_mc._y - 42;
      button.lineStyle(2,16777215,100);
      button.beginFill(16234264,100);
      button.moveTo(6,0);
      button.lineTo(64,0);
      button.curveTo(70,0,70,6);
      button.lineTo(70,20);
      button.curveTo(70,26,64,26);
      button.lineTo(6,26);
      button.curveTo(0,26,0,20);
      button.lineTo(0,6);
      button.curveTo(0,0,6,0);
      button.endFill();
      button.createTextField("label_txt",1,3,4,64,18);
      var format = new TextFormat("_sans",11,478067,true);
      format.align = "center";
      button.label_txt.setNewTextFormat(format);
      button.label_txt.text = "TRADE";
      button.label_txt.selectable = false;
      button.useHandCursor = true;
   }
   button._visible = true;
   button.onRelease = function()
   {
      var playerId = getActivePlayerId();
      var nickname = escape(getActivePlayerNickname());
      getURL("penguin-trade://open?target=" + playerId + "&name=" + nickname,"_blank");
      closeHint();
   };
   button.onRollOver = function()
   {
      showHint(this,"Trade",0,-28,false);
   };
   button.onRollOut = closeHint;
}
function showRemoveBuddyButton()
{'''

menu_replacement = '''   showStampBookButton();
   if(playerRelationship == "Player" || playerRelationship == "Mascot" || playerRelationship == "MascotFriend")
   {
      hideTradeButton();
   }
   else
   {
      showTradeButton();
   }
   if(shell.playerModel.isPlayerModerator())'''

if "function showTradeButton()" not in text:
    if function_anchor not in text or menu_anchor not in text:
        raise SystemExit("The interface client does not match the supported player-card script.")
    text = text.replace(function_anchor, trade_functions, 1)
    text = text.replace(menu_anchor, menu_replacement, 1)
    source.write_text(text, encoding="utf-8", newline="\n")
