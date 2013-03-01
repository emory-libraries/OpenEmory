$(function() {
    $("input[type=submit]").addClass("submit");
    $("input[type=reset]").addClass("reset");
    $("input[type=button]").addClass("button");
    $("input[type=checkbox]").addClass("checkbox");
    $("input[type=radio]").addClass("radio");
    $("li").hover(function() {
        $(this).addClass("hover");
    }, function() {
        $(this).removeClass("hover");
    });
});