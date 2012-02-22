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
});