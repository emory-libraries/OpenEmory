/* * * * * Misc. jQuery application of design * * * * */

/* SHARED PAGE TEMPLATE STYLES */

$(function () {
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
});