/**

jQuery to lookup a username input value and set the returned values in
author name input fields on an edit form.  

Example usage:

  $(".netid-lookup").userLookup({
    url: "/accounts/USERNAME/name/",
    url_replace: "USERNAME",
  });


If url_replace is specified, the url_replace string will be replaced 
with the value of the input field before making the Ajax request.

*/
(function($){
  var plugin_name = 'userLookup';
  var methods = {
      init : function(options) { 
          // options must include url value
          var settings = {
              csrftoken: $(document).find('input[name=csrfmiddlewaretoken]').val(),
              modified: false,
          };
          if (options) {
              $.extend(settings, options);
          }
          return this.each(function(){
              var input = $(this);
              // store settings on the objects data with plugin name
              input.data(plugin_name, settings);
              // bind event methods
              input.focusout(methods.focusout);
              input.change(methods.change);
          });
      },  // end init

      focusout: function() {
          var input = $(this);
          var value = input.val();
          // if unchanged since last lookup, don't do anything
          if ( ! input.data(plugin_name).modified ) { 
              return; 
          }
          // if changed and now empty, blank out previous values
          if ( ! value ) {
            input.userLookup('updateform');
            return;
          }
          var url = input.data(plugin_name).url;
          if (input.data(plugin_name).url_replace) {
              url = url.replace(input.data(plugin_name).url_replace, value);
          }
          // if a value is set, post the username and update form 
          $.ajax({
              type: 'GET', 
              url: url,
              dataType: 'json',
              success: function(data, status, xhr) {
                  input.userLookup('updateform', data);
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
                  input.userLookup('updateform');
                  // display a fading message with error detail
                  input.parent().fadingMessage({text: msg, class: 'error',
	                                        delay: 3000});
              },
              complete: function(xhr, status) {
                  // either sucess or failure, set field to not
                  // modified since last lookup
                  input.data(plugin_name).modified = false;
              },
          });
      },
    
    change: function() {
        var input = $(this);
        input.data(plugin_name).modified = true;
    },

    updateform: function(data) {
        var input = $(this);
        var formdiv = input.closest('div');  // container for current author formset form
        var fields = {
            // find inputs that end with the name (number will vary, due to formset)
            id_name: formdiv.find('input[name$="id"]'),
            family_name: formdiv.find('input[name$="family_name"]'),
            given_name:  formdiv.find('input[name$="given_name"]'),
            affiliation: formdiv.find('input[name$="affiliation"]'),
        };
        if (data) {
            fields.id_name.attr('value', data.username); // normalize id based on result
            fields.family_name.attr('value', data.last_name);
            fields.given_name.attr('value', data.first_name);

            fields.affiliation.attr('value', 'Emory University');
            fields.affiliation.addClass('readonly');
            fields.affiliation.attr('readonly', 'readonly');
            fields.affiliation.attr('tabindex', '-1');
        } else { // no data - clear out fields
            fields.family_name.attr('value', '');
            fields.given_name.attr('value', '');

            fields.affiliation.attr('value', '');
            fields.affiliation.removeClass('readonly');
            fields.affiliation.removeAttr('readonly');
            fields.affiliation.removeAttr('tabindex')
        }
    },

  }; // end methods

  $.fn.userLookup = function( method ) {
    // Method calling logic
    if ( methods[method] ) {
      return methods[ method ].apply( this, Array.prototype.slice.call( arguments, 1 ));
    } else if ( typeof method === 'object' || ! method ) {
      return methods.init.apply( this, arguments );
    } else {
      $.error('Method ' +  method + ' does not exist on jQuery.' + plugin_name);
    }    
  
  };


})( jQuery );

