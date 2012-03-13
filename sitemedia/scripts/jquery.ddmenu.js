var timeout    = 500;
var closetimer = 0;
var ddmenuitem = 0;
var lastparent = 0;

function jsddm_open() {  
	jsddm_canceltimer();
   	jsddm_close();
   	ddmenuitem = $(this).find('ul.dd_content').css('visibility', 'visible');
   	lastparent = $(this);
	$(this).css('background-color', '#3354B5');   
}

function jsddm_close() {  
	if(ddmenuitem) {
		ddmenuitem.css('visibility', 'hidden');
	}
	
	if (lastparent)
		lastparent.css('background-color', '#04207C');
}

function jsddm_timer() {  
	closetimer = window.setTimeout(jsddm_close, timeout);
}

function jsddm_canceltimer() {  
	if(closetimer) {  
		window.clearTimeout(closetimer);
      	closetimer = null;
    }
}

$(document).ready(function() {  
	$('#jsddm > li.dd_parent').bind('mouseover', jsddm_open)
   	$('#jsddm > li.dd_parent').bind('mouseout',  jsddm_timer)
});

document.onclick = jsddm_close;