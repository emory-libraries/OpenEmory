/* ajax functionality for ingesting items in the harvest queue */
$(document).ready(function () {
    // pick up the csrf token for use in all ajax requests
    var csrftoken = $("#csrftoken input").attr("value");

    // NOTE: There is some overlap in ingest/ignore functionality
    // below (particularly success/error handling and message
    // display), but it is not obvious how to combine them.

    // configure ingest buttons to POST pmcid when clicked
    $(".ingest").click(function() {
        var data = { pmcid: $(this).find(".pmcid").html()};
        var entry = $(this).parent();
        var msg = entry.find('.message');
        var errclass = 'error-msg';
        var success_class = 'success-msg';

        if ( ! entry.hasClass('working') ) {
          entry.addClass('working');
          $.ajax({
              type: 'POST',
              data: data,
              url: $(this).attr('href'),
              headers: {'X-CSRFTOKEN': csrftoken},
              success: function(data, status, xhr) {
                  msg.html(data || 'Success');
                  msg.removeClass(errclass).addClass(success_class).show().delay(1500).fadeOut();
                  // change queue item class on success so display can be updated
                  entry.removeClass('working').addClass('ingested');
              },
              error: function(data, status, xhr) {
                  msg.html('Error: ' + data.responseText);
                  msg.removeClass(success_class).addClass(errclass).show();
                  // NOTE: not fading error message out, since it may
                  // need to be reported
              }

          });
        }
        return false;
    });

    // configure ignore buttons to DELETE specified url when clicked
    $(".ignore").click(function() {
        var entry = $(this).parent();
        var msg = entry.find('.message');
        var errclass = 'error-msg';
        var success_class = 'success-msg';

        if ( ! entry.hasClass('working') ) {
          entry.addClass('working');
          $.ajax({
              type: 'DELETE',
              url: $(this).attr('href'),
              headers: {'X-CSRFTOKEN': csrftoken},
              success: function(data, status, xhr) {
                  msg.html(data || 'Success');
                  msg.removeClass(errclass).addClass(success_class).show().delay(1500).fadeOut();
                  // change queue item on success so display can be updated
                  entry.removeClass('working').addClass('ignored');
              },
              error: function(data, status, xhr) {
                  msg.html('Error: ' + data.responseText);
                  msg.removeClass(success_class).addClass(errclass).show();
              }

          });
        }
        return false;
    });

});


