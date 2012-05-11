/**

jQuery plugin for displaying brief messages that will fade out.

Usage examples:

  $("#container").fadingMessage({text: 'Saved'});
  $("#container").fadingMessage({text: 'Failed to save', class: 'error'});

Default message class is 'message'; default status class is 'success'.
Messages are appended to the element specified.  When displaying a new
message, any previous elements with the message class will be removed
from the container element.

*/


(function( $ ){
  $.fn.fadingMessage = function(options){
      if (options == null) {
          options = {};
      }

      // default settings
      var settings = {
          message_class: 'message',
          text: '',
          class: 'success',
          delay: 1000,
          fade: 1500
      };
      if (options) {
          $.extend(settings, options);
      }
          
      return this.each(function(){
          $(this).find('.' + settings.message_class).remove();
          $('<span/>').addClass(settings.message_class)
              .html(settings.text).addClass(settings.class).appendTo(this)
              .delay(settings.delay).fadeOut(settings.fade);
      });
  };

})( jQuery );


