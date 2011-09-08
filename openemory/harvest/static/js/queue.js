/* ajax functionality for ingesting items in the harvest queue */
$(document).ready(function () {
    // pick up the csrf token for use in all ajax requests
    var csrftoken = $("#csrftoken input").attr("value");

    // configure ingest buttons to POST pmcid when clicked
    $(".ingest").click(function() {
        var data = { pmcid: $(this).find(".pmcid").html()};
        var msg = $(this).parent().find('.message');
        var errclass = 'error-msg';
        var success_class = 'success-msg';
        $.ajax({
            type: 'POST',
            data: data,
            url: $(this).attr('href'),
            headers: {'X-CSRFTOKEN': csrftoken},
            success: function(data, status, xhr) {
                msg.html('Success');
                msg.removeClass(errclass).addClass(success_class).show();
                // hide the whole queue item on success
                msg.parents('.queue-item').delay(1500).fadeOut();
            },
            error: function(data, status, xhr) {

                msg.html('Error: ' + data.responseText);
                msg.removeClass(success_class).addClass(errclass).show();
                // should error message disappear ? 
                //msg.delay(1500).fadeOut();
            }

        });
        return false;
    });
});
