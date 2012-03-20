/* * * * * Misc. jQuery application of design * * * * */

/* SHARED PAGE TEMPLATE STYLES */

function common_init(){
	$("div.globalContact").hide();
	$("a.contactToggle").click(function () {
		var $globalContact = $(this).next("div.globalContact");
		if ($globalContact.is(':hidden')) {
			$globalContact.slideDown();
			$(this).children().html('Collapse Contact Us');
		}
		else {
			$globalContact.slideUp();
			$(this).children().html('Contact Us');
		}
		return false;
	});


    /** abstract pop-up */
    // show abstract popup on viewAbstract click
    $('a.viewAbstract').click(function (e) {
        e.preventDefault();
        x = $(this).position().left - 528;
        y = $(this).position().top - 70;
        // find the first parent that contains an abstract popup; set position and toggle display
        abs = $(this).parents(':has(.viewAbstractPopup)').first().find('.viewAbstractPopup');
        abs.css({ 'top': y, 'left': x }).toggle();
    })
    // hide popup on close
    $('.viewAbstractPopup a.closeBlue').click(function (e) {
        e.preventDefault();
        $(this).parents('.viewAbstractPopup').hide();
    });
    
    $("a.tip[title]").tooltip({
    	offset: [5, 0], 
    	layout:"<div/>",
    	tipInner: "span"
    });
    
    $("input[type=file]").filestyle({
    	imageheight: 22,
    	imagewidth: 95,
    	width: 120,
    	btnText: "Choose File"
    });
}

// bind common initialization: run on document load and after an ajax load completes
$(document).ready(function(){ common_init(); });
$(document).ajaxComplete(function(){ common_init(); });


// update altList so only visible odd rows have alternate class
// expects a container element that includes a ul.altList
function update_alternates(el) {
  el.find("ul.altList li:visible").each(function(i){
      if (i % 2) { $(this).removeClass("alternate"); }
      else { $(this).addClass("alternate"); }
  });
}

$(document).ready(function () {
 //login input functionality
    // username functionality
    $('input.text:text').focus(function () {
        if ($(this).val() == this.defaultValue) {
        	$(this).val('');
        }
    });

    $('input.text:text').blur(function () {
        if ($(this).val() == '') {
            $(this).val(this.defaultValue);
        }
    });

    // show input default text and hide password type input

    $('#password-clear').show();
    $('#password').hide();

    // password functionality
    $('#password-clear').focus(function () {
        $('#password-clear').hide();
        $('#password').show();
        $('#password').focus();
    });

   $('#password').blur(function () {
       if ($('#password').val() == '') {
           $('#password-clear').show();
           $('#password').hide();
       }

   });

   $("#search-button").click(function(event) {
       $('#search-form').submit();
   });

});
