"""
  HTML reader/writer for RichText
"""


import re

from HTMLParser import HTMLParser


from takenote.gui.textbuffer_tools import \
     iter_buffer_contents, \
     buffer_contents_iter_to_offset, \
     normalize_tags, \
     insert_buffer_contents, \
     buffer_contents_apply_tags

from takenote.gui.richtextbuffer import \
     IGNORE_TAGS, \
     add_child_to_buffer, \
     RichTextBuffer, \
     RichTextImage, \
     RichTextHorizontalRule, \
     RichTextError




class HtmlError (StandardError):
    """Error for HTML parsing"""
    pass


# TODO: may need to include support for ignoring information between
# <scirpt> and <style> tags

class HtmlBuffer (HTMLParser):
    """Read and write HTML for a RichTextBuffer"""
    
    def __init__(self, out=None):
        HTMLParser.__init__(self)
    
        self._out = out
        self._mod_tags = "biu"
        self._mod_tag2buffer_tag = {
            "b": "Bold",
            "i": "Italic",
            "u": "Underline"}
        self._buffer_tag2mod_tag = {
            "Bold": "b",
            "Italic": "i",
            "Underline": "u"
            }
        self._buffer_tag2html = {
            "Left": "left",
            "Center": "center",
            "Right": "right",
            "Justify": "justify"}
        self._html2buffer_tag = {
            "left": "Left",
            "center": "Center",
            "right": "Right",
            "justify": "Justify"}
        self._newline = False

        self._tag_stack = []
        self._butter_contents = []
        self._text_queue = []
        self._within_body = False
        self._partial = False
        
        self._entity_char_map = [("&", "amp"),
                                (">", "gt"),
                                ("<", "lt"),
                                (" ", "nbsp")]
        self._entity2char = {}
        for ch, name in self._entity_char_map:
            self._entity2char[name] = ch
        
        self._charref2char = {"09": "\t"}
        
        
        
    
    def set_output(self, out):
        """Set the output stream for HTML"""
        self._out = out


    #===========================================
    # Reading HTML
    
    def read(self, infile, partial=False, ignore_errors=False):
        """Read from stream infile to populate textbuffer"""
        self._text_queue = []
        self._within_body = False
        self._buffer_contents = []
        self._partial = partial


        try:
            for line in infile:
                self.feed(line)

                # yeild items read so far
                for item in self._buffer_contents:
                    yield item
                self._buffer_contents[:] = []
        
            self.close()
            self.flush_text()
        
            # yeild remaining items
            for item in self._buffer_contents:
                yield item
            self._buffer_contents[:] = []
            
        except Exception, e:
            # reraise error if not ignored
            if not ignore_errors:
                raise
        
        
    def flush_text(self):
        if len(self._text_queue) > 0:
            text = "".join(self._text_queue)
            if len(text) > 0:
                self._buffer_contents.append(("text", None, text))
                self._text_queue[:] = []

            
    def queue_text(self, text):
        self._text_queue.append(text)

    def append_buffer_item(self, kind, param):
        self.flush_text()        
        self._buffer_contents.append((kind, None, param))

    def parse_style(self, stylestr):
        """Parse a style attribute"""

        # TODO: this parsing may be too simplistic
        for statement in stylestr.split(";"):
            statement = statement.strip()
            
            tagstr = None
        
            if statement.startswith("font-size"):
                # font size
                size = int("".join(filter(lambda x: x.isdigit(),
                                   statement.split(":")[1])))
                tagstr = "size " + str(size)
                        
            elif statement.startswith("font-family"):
                # font family
                tagstr = statement.split(":")[1].strip()

            elif statement.startswith("text-align"):
                align = statement.split(":")[1].strip()

                # TODO: simplify
                tagstr = self._html2buffer_tag.get(align, None)
                if tagstr is None:
                    raise HtmlError("unknown justification '%s'" % align)

            else:
                # ignore other styles
                pass
        
            if tagstr is not None:
                self.append_buffer_item("beginstr", tagstr)
                self._tag_stack[-1][1].append(tagstr)


    def parse_image(self, attrs):
        """Parse image tag and return image child anchor"""
        
        img = RichTextImage()
        width, height = None, None
            
        for key, value in attrs:
            if key == "src":
                img.set_filename(value)
                    
            elif key == "width":
                try:
                    width = int(value)
                except ValueError, e:
                    # ignore width if we cannot parse it
                    pass
                
            elif key == "height":
                try:
                    height = int(value)
                except ValueError, e:
                    # ignore height if we cannot parse it
                    pass
                
            else:
                # ignore other attributes
                pass
            

        img.set_size(width, height)
        return img
        
    
    def handle_starttag(self, htmltag, attrs):
        """Callback for parsing a starting HTML tag"""
        
        self._newline = False

        # start a new tag on htmltag stack
        self._tag_stack.append((htmltag, []))

        if htmltag == "html":
            # ignore html tag
            pass
        
        elif htmltag == "body":
            # note that we are no within the body tag
            self._within_body = True
        
        elif htmltag in self._mod_tag2buffer_tag:
            # simple font modifications (b/i/u)
            
            tagstr = self._mod_tag2buffer_tag[htmltag]
            self.append_buffer_item("beginstr", tagstr)
            self._tag_stack[-1][1].append(tagstr)

        elif htmltag == "span":
            # apply style
            
            for key, value in attrs:
                if key == "style":
                    self.parse_style(value)
                else:
                    # ignore other attributes
                    pass
        
        elif htmltag == "div":
            # text justification
            
            for key, value in attrs:
                if key == "style":
                    self.parse_style(value)
                else:
                    # ignore other attributes
                    pass

        elif htmltag == "p":
            # paragraph
            # NOTE: this tag is currently not used by TakeNote, but if pasting
            # text from another HTML source, TakeNote will interpret it as
            # a newline char
            self.queue_text("\n")
            
        elif htmltag == "br":
            # insert newline
            self.queue_text("\n")
            self._newline = True
            
        elif htmltag == "hr":
            # horizontal break
            hr = RichTextHorizontalRule()
            self.append_buffer_item("anchor", (hr, None))
    
        elif htmltag == "img":
            # insert image
            img = self.parse_image(attrs)
            self.append_buffer_item("anchor", (img, None))

        else:
            # ingore other html tags
            pass
        
        


    def handle_endtag(self, htmltag):
        """Callback for parsing a ending HTML tag"""
        
        self._newline = False
        if not self._partial:
            if htmltag in ("html", "body") or not self._within_body:
                return

        if len(self._tag_stack) == 0:
            return
        
        htmltag2, tags = self._tag_stack.pop()
        
        # ensure closing tags match opened tags
        while len(self._tag_stack) > 0 and htmltag2 != htmltag:
            html2, tags = self._tag_stack.pop()
            #raise HtmlError("closing tag does not match opening tag")

        for tagstr in tags:
            self.append_buffer_item("endstr", tagstr)
        
        if htmltag == "p":
            # paragraph tag
            self.queue_text("\n")

    
    
    def handle_data(self, data):
        """Callback for character data"""

        if not self._partial and not self._within_body:
            return
        
        if self._newline:
            data = re.sub("\n[\n ]*", "", data)
            self._newline = False
        else:
            data = re.sub("[\n ]+", " ", data)
        self.queue_text(data)

    
    def handle_entityref(self, name):
        if not self._partial and not self._within_body:
            return
        self.queue_text(self._entity2char.get(name, ""))
    
    
    def handle_charref(self, name):
        if not self._partial and not self._within_body:
            return
        self.queue_text(self._charref2char.get(name, ""))



    #================================================
    # Writing HTML
    
    def write(self, buffer_content, partial=False):
        
        if not partial:
            self._out.write("""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<body>""")
        
        for kind, it, param in normalize_tags(buffer_content):
            if kind == "text":
                text = param
                
                # TODO: could try to speed this up
                text = text.replace("&", "&amp;")
                text = text.replace(">", "&gt;")
                text = text.replace("<", "&lt;")
                text = text.replace("\n", "<br/>\n")
                text = text.replace("\t", "&#09;")
                text = text.replace("  ", " &nbsp;")
                self._out.write(text)
            
            elif kind == "begin":
                tag = param
                self.write_tag_begin(tag)
                
            elif kind == "end":
                tag = param
                self.write_tag_end(tag)
            
            elif kind == "anchor":
                child = param[0]

                if isinstance(child, RichTextImage):
                    # write image
                    size_str = ""
                    size = child.get_size()
                        
                    if size[0] is not None:
                        size_str += " width=\"%d\"" % size[0]
                    if size[1] is not None:
                        size_str += " height=\"%d\"" % size[1]
                        
                    self._out.write("<img src=\"%s\" %s />" % 
                                   (child.get_filename(), size_str))

                elif isinstance(child, RichTextHorizontalRule):
                    self._out.write("<hr/>")
                    
                else:
                    # warning
                    #TODO:
                    print "unknown child element", child
            
            elif kind == "pixbuf":
                pass
            else:
                raise Exception("unknown kind '%s'" % str(kind))

        if not partial:
            self._out.write("</body></html>")
        
    
    def write_tag_begin(self, tag):
        tagname = tag.get_property("name")

        
        if tagname in IGNORE_TAGS:
            pass
        
        elif tagname in self._buffer_tag2mod_tag:
            self._out.write("<%s>" % self._buffer_tag2mod_tag[tagname])
                    
        elif tagname.startswith("size "):
            self._out.write("<span style='font-size: %dpt'>" % 
                            tag.get_property("size-points"))

        elif tagname in self._buffer_tag2html:
            text = self._buffer_tag2html[tagname]
            self._out.write("<div style='text-align: %s'>" % text)
                
        elif tag.get_property("family") is not None:
            self._out.write("<span style='font-family: %s'>" % 
                            tag.get_property("family"))
                
        else:
            raise HtmlError("unknown tag '%s'" % tag.get_property("name"))
                
        
    def write_tag_end(self, tag):
        tagname = tag.get_property("name")
        
        if tagname in self._buffer_tag2mod_tag:
            self._out.write("</%s>" % self._buffer_tag2mod_tag[tagname])
                            
        elif tag in self._buffer_tag2html:
            self._out.write("</div>")
            
        else:
            self._out.write("</span>")

