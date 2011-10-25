/**
jQuery to lookup a username input value and set the returned values in
author name input fields on an edit form.  
*/
(function($){
  $.fn.userLookup = function(options){
      // options must include url value
      var settings = {
          csrftoken: $(document).find('input[name=csrfmiddlewaretoken]').val(),
      };
      if (options) {
          $.extend(settings, options);
      }
          
      return this.each(function(){
          var input = $(this);
          var formdiv = input.closest('div');  // container for current author formset form
          var fields = {
              // find inputs that end with the name (number will vary, due to formset)
              family_name: formdiv.find('input[name$="family_name"]'),
              given_name:  formdiv.find('input[name$="given_name"]'),
              affiliation:  formdiv.find('input[name$="affiliation"]'),
          };
          input.focusout(function() {  
              var value = input.val();
              if (value) { 
                  // if a value is set, post the username and update form 
                  $.ajax({
                      type: 'POST', 
                      url: settings.url,
                      data: {username: value},
                      // pass Django CSRF token 
                      headers: {'X-CSRFTOKEN': settings.csrftoken},
                      success: function(data, status, xhr) {
                          fields.family_name.attr('value', data.last_name);
                          fields.given_name.attr('value', data.first_name);
                          fields.affiliation.attr('value', 'Emory University');
                      },
                      error: function(xhr, status, error) {
                          if (xhr.status == 404) {  // user not found in local db or ldap
                              msg = 'User not found';
                          } else { // 500 (uncaught exception)
             	              msg = 'Failed to look up user - ' + status.ucfirst();
                              if (xhr.getResponseHeader('Content-Type') == 'text/plain') {
                                  msg += ': ' + xhr.responseText
                              }
                          }
                          // blank out any previous values
                          fields.family_name.attr('value', '');
                          fields.given_name.attr('value', '');
                          fields.affiliation.attr('value', '');
                          // display a fading message with error detail
                          input.parent().fadingMessage({text: msg, class: 'error',
	                                                delay: 3000});
                      },
                  });
                  
              } // end if value
          }); // end focus out
      }); 

  };

})( jQuery );

